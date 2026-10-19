"""Tests for the link between the router and the portal.

When a complaint is registered the portal keeps the router's message to the citizen, and the router's timeline
(the charter's repair time and its escalation days). The screens show the message at once and show the timeline
as the complaint's progress. No LLM or internet is needed: complaints are filed with the keyword classifier.
"""

import http.client
import importlib.util
import json
import sqlite3
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "complaint_tools"))

# pylint: disable=wrong-import-position
from complaintrouter.common import load_charter  # noqa: E402
from complaintrouter.pipeline import run_complaint  # noqa: E402
from complaintrouter.reply import BANNER  # noqa: E402
from complaint_portal.auth import Sessions, hash_password  # noqa: E402
from complaint_portal.rules import DEPOT, DISTRICT_HEAD, FIELDS, WARD  # noqa: E402
from complaint_portal.store import Store  # noqa: E402
from complaint_portal.workflow import Portal  # noqa: E402

_spec = importlib.util.spec_from_file_location("portal_server", ROOT / "portal" / "server.py")
portal_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(portal_server)

CHARTER = load_charter()
NOW = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
HASH = hash_password("portal-test-pass")  # hashed once so the tests stay fast
LEAK = "Water is leaking from the pipe near my house for three days, please fix it."
SEWER = "Sewer main is blocked, manhole overflowing on our street, no action in 10 days"
BILL = "My water bill is wrong, the charges are too high this month"
NEW_CONN = "I applied for a new connection two months ago and it is still pending"
CONTACT = "9876543210"
WARD_NUMBER = 115
LEVELS = ["depot", "deputy_ae", "area_engineer", "superintendent_engineer"]


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "portal.db")


@pytest.fixture
def portal(store):
    return Portal(store)


@pytest.fixture
def staffed(store):
    for field in FIELDS:
        for level in LEVELS:
            store.insert_officer(f"{field}.{level}", f"{FIELDS[field]} {level}", field, level, HASH)
    store.insert_officer("district.head", "District Head Office", "all", DISTRICT_HEAD, HASH)
    return store


def file_complaint(portal, text=LEAK, now=NOW):
    return portal.register("Ravi Kumar", CONTACT, text, ward_number=WARD_NUMBER, use_llm=False, now=now)


def days(count):
    return f"{count} day" if count == 1 else f"{count} days"


# ---------------------------------------------------------------- the router's message at registration

def test_message_is_the_routers_own_text_with_the_real_complaint_id(portal, staffed):
    view = file_complaint(portal)
    expected = run_complaint(LEAK, None, use_llm=False, reference=view["id"])["reply"]
    assert view["router_message"] == expected          # not reworded, not shortened
    assert view["router_message"].startswith(BANNER)
    assert f"Complaint reference: {view['id']}" in view["router_message"]
    assert "to be assigned" not in view["router_message"]


def test_the_router_alone_still_says_the_reference_is_to_be_assigned():
    reply = run_complaint(LEAK, None, use_llm=False)["reply"]
    assert "Complaint reference: (reference to be assigned)" in reply


def test_message_is_kept_with_the_complaint_and_returned_when_it_is_tracked(store, portal, staffed):
    view = file_complaint(portal)
    assert store.get_complaint(view["id"])["router_message"] == view["router_message"]
    tracked = portal.track(view["id"], CONTACT)
    assert tracked["router_message"] == view["router_message"]


def test_message_carries_the_charter_timeline_and_helplines(portal, staffed):
    message = file_complaint(portal)["router_message"]
    assert "Charter timeline for repair: 3 days" in message
    assert f"call toll free {CHARTER['helplines']['toll_free']}" in message
    assert "Escalation days as printed in the charter, per officer level:" in message


# ---------------------------------------------------------------- the router's timeline as progress

@pytest.mark.parametrize("text", [LEAK, SEWER, BILL, NEW_CONN])
def test_progress_is_the_routers_timeline_for_each_kind_of_complaint(portal, staffed, text):
    view = file_complaint(portal, text)
    result = run_complaint(text, None, use_llm=False)
    timeline, escalation = result["timeline"], result["escalation"]
    progress = view["router_progress"]
    steps = progress["steps"]

    assert progress["label"] == timeline["label"]
    assert progress["kept_at_registration"] is True
    assert steps[0]["stage"] == DEPOT and steps[0]["state"] == "current"
    # The depot's time is the charter repair time. A complaint type with no repair time (billing) uses the depot's
    # escalation days instead. Either way it is the time the portal really counts down to.
    printed_depot = escalation["levels_as_printed"][0]["days"] if escalation["applies"] else None
    depot_days = timeline["fix_days"] if timeline["fix_days"] is not None else printed_depot
    assert steps[0]["time_limit"] == days(depot_days)
    assert datetime.fromisoformat(view["deadline"]) - NOW == timedelta(days=depot_days)
    assert steps[-1]["stage"] == DISTRICT_HEAD and steps[-1]["state"] == "upcoming"
    assert all(step["state"] == "upcoming" for step in steps[1:])
    if escalation["applies"]:
        printed = dict(zip(CHARTER["stage_order"], escalation["levels_as_printed"]))
        for step in steps[1:-1]:                                       # the levels between the depot and the end
            assert step["time_limit"] == days(printed[step["stage"]]["days"]), step
        assert progress["after_last_level"] == escalation["after_last_level"]
        assert progress["note"] == escalation["note"]


def test_the_current_step_carries_the_live_deadline(portal, staffed):
    view = file_complaint(portal)
    current = [step for step in view["router_progress"]["steps"] if step["state"] == "current"]
    assert len(current) == 1 and current[0]["deadline"] == view["deadline"]


def test_progress_moves_up_when_a_time_limit_passes(store, portal, staffed):
    view = file_complaint(portal)
    assert portal.check_overdue(NOW + timedelta(days=4)) == [view["id"]]
    steps = portal.track(view["id"], CONTACT)["router_progress"]["steps"]
    assert [step["state"] for step in steps] == ["done", "current", "upcoming", "upcoming", "upcoming"]
    assert steps[1]["stage"] == "deputy_ae" and steps[1]["time_limit"] == "2 days"
    assert steps[1]["deadline"] == store.get_complaint(view["id"])["stage_deadline"]


def test_progress_shows_the_ward_office_when_the_citizen_says_not_fixed(store, portal, staffed):
    view = file_complaint(portal)
    portal.resolve(store.get_officer(store.get_complaint(view["id"])["assigned_officer_id"]), view["id"],
                   "Clamp fitted.", now=NOW + timedelta(hours=2))
    portal.confirm(view["id"], CONTACT, False, "Still leaking", now=NOW + timedelta(days=1))
    steps = portal.track(view["id"], CONTACT)["router_progress"]["steps"]
    assert [step["stage"] for step in steps] == [DEPOT, WARD, DISTRICT_HEAD]
    assert [step["state"] for step in steps] == ["done", "current", "upcoming"]
    assert steps[1]["time_limit"] == "3 days, the same as the depot"


def test_progress_for_a_closed_complaint_marks_what_it_did_not_need(store, portal, staffed):
    view = file_complaint(portal)
    portal.resolve(store.get_officer(store.get_complaint(view["id"])["assigned_officer_id"]), view["id"],
                   "Pipe repaired.", now=NOW + timedelta(hours=5))
    asked = portal.confirm(view["id"], CONTACT, True, "Thanks", now=NOW + timedelta(days=1))
    portal.confirm_code(view["id"], CONTACT, asked["demo_code"], now=NOW + timedelta(days=1))
    steps = portal.track(view["id"], CONTACT)["router_progress"]["steps"]
    assert steps[0]["state"] == "done"
    assert all(step["state"] == "skipped" for step in steps[1:])
    assert not any("deadline" in step for step in steps)


# ---------------------------------------------------------------- older complaints and older databases

def test_a_complaint_filed_before_the_link_still_shows_the_routers_timeline(store, portal, staffed):
    old = file_complaint(portal)
    expected_steps = old["router_progress"]["steps"]
    with sqlite3.connect(store.path) as conn:
        conn.execute("UPDATE complaints SET router_message = NULL, router_timeline = NULL WHERE id = ?", (old["id"],))
    tracked = portal.track(old["id"], CONTACT)
    assert tracked["router_message"] is None                           # a message that was never kept is not invented
    assert tracked["router_progress"]["kept_at_registration"] is False
    assert tracked["router_progress"]["steps"] == expected_steps       # same timeline, from the router's own tools


@pytest.mark.skipif(sqlite3.sqlite_version_info < (3, 35), reason="needs DROP COLUMN")
def test_an_older_database_gets_the_new_columns(tmp_path):
    path = tmp_path / "old.db"
    Store(path)
    with sqlite3.connect(path) as conn:
        conn.execute("ALTER TABLE complaints DROP COLUMN router_message")
        conn.execute("ALTER TABLE complaints DROP COLUMN router_timeline")
    Store(path)                                                        # opening it upgrades it
    with sqlite3.connect(path) as conn:
        names = {row[1] for row in conn.execute("PRAGMA table_info(complaints)")}
    assert {"router_message", "router_timeline"} <= names


# ---------------------------------------------------------------- over HTTP, as the screens use it

@pytest.fixture
def site(tmp_path):
    httpd = portal_server.make_server("127.0.0.1", 0, Portal(Store(tmp_path / "portal.db")), Sessions(), Sessions(),
                                      web_dir=tmp_path / "web")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    yield f"{host}:{port}"
    httpd.shutdown()
    httpd.server_close()


def post_json(address, path, payload, cookie=None):
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    request = urllib.request.Request(f"http://{address}{path}", data=json.dumps(payload).encode("utf-8"),
                                     headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.headers, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, error.headers, json.loads(error.read() or b"{}")


def test_registering_over_http_returns_the_message_and_timeline_straight_away(site):
    assert post_json(site, "/api/citizen/signup", {"name": "Test Citizen", "contact": CONTACT,
                                                   "address": "12 Main Road, Teynampet", "ward_number": 1})[0] == 201
    code = post_json(site, "/api/citizen/login", {"contact": CONTACT})[2]["code"]
    _, headers, _ = post_json(site, "/api/citizen/verify", {"contact": CONTACT, "code": code})
    cookie = headers.get_all("Set-Cookie")[0].split(";")[0]

    status, _, view = post_json(site, "/api/complaints", {"complaint": LEAK, "use_llm": False}, cookie=cookie)
    assert status == 201, view
    assert view["router_message"].startswith(BANNER)
    assert f"Complaint reference: {view['id']}" in view["router_message"]
    assert view["router_progress"]["steps"][0]["state"] == "current"

    status, _, tracked = post_json(site, "/api/track", {"id": view["id"], "contact": CONTACT})
    assert status == 200
    assert tracked["router_message"] == view["router_message"]
    assert tracked["router_progress"] == view["router_progress"]


# ---------------------------------------------------------------- the screens are wired to it

def test_the_web_pages_and_the_app_show_the_routers_message_and_timeline():
    register = (ROOT / "portal" / "register.html").read_text(encoding="utf-8")
    track = (ROOT / "portal" / "track.html").read_text(encoding="utf-8")
    assert "Portal.routerMessage(view.router_message" in register and "Portal.routerProgress(view.router_progress)" in register
    assert "Coming soon" not in register                               # the empty "From the agents" box is filled now
    assert "Portal.routerProgress(view.router_progress)" in track and "Portal.routerMessage(view.router_message)" in track

    app = ROOT / "flutter_app" / "lib"
    done = (app / "screens" / "register_complaint_screen.dart").read_text(encoding="utf-8")
    tracked = (app / "screens" / "track_complaint_screen.dart").read_text(encoding="utf-8")
    assert "RouterMessage(message: view['router_message']" in done and "COMING SOON" not in done
    assert "RouterProgress(progress: view['router_progress'])" in tracked
    assert (app / "widgets" / "router_panels.dart").exists()
