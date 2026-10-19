"""Tests for the complaint portal: routing, time limits, escalation, citizen confirmation,
officer access, and the web API.

No LLM or internet is needed. Each test uses its own temporary database. Times are passed in
explicitly, so escalation can be tested without waiting.
"""

import importlib.util
import json
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
from complaint_portal.auth import Sessions, hash_password, verify_password  # noqa: E402
from complaint_portal.rules import (  # noqa: E402
    AWAITING,
    CLOSED,
    DEPOT,
    DISTRICT_HEAD,
    FIELD_FOR_TYPE,
    FIELDS,
    OPEN,
    stage_path,
    stage_window,
)
from complaint_portal.seed import seed_demo_officers  # noqa: E402
from complaint_portal.store import Store  # noqa: E402
from complaint_portal.workflow import PortalError, Portal, iso  # noqa: E402

# The app folder also has a server.py, so load the portal's server under its own name.
_spec = importlib.util.spec_from_file_location("portal_server", ROOT / "portal" / "server.py")
portal_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(portal_server)

CHARTER = load_charter()
NOW = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
PASSWORD = "portal-test-pass"
HASH = hash_password(PASSWORD)  # hashed once; every test account reuses it, so tests stay fast
LEAK = "Water is leaking from the pipe near my house for three days, please fix it."
SEWER = "Sewer main is blocked, manhole overflowing on our street, no action in 10 days"
BILL = "My water bill is wrong, the charges are too high this month"
NEW_CONN = "I applied for a new connection two months ago and it is still pending"
CONTACT = "98765 43210"
WARD = 115  # ward 115 is in zone 9, Teynampet
ADDRESS = "14 Pillaiyar Koil Street, Teynampet, Chennai 600018"
LEVELS = ["depot", "deputy_ae", "area_engineer", "superintendent_engineer"]


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "portal.db")


@pytest.fixture
def portal(store):
    return Portal(store)


@pytest.fixture
def staffed(store):
    """One officer per field and level, plus the District Head Office."""
    for field in FIELDS:
        for level in LEVELS:
            store.insert_officer(f"{field}.{level}", f"{FIELDS[field]} {level}", field, level, HASH)
    store.insert_officer("district.head", "District Head Office", "all", DISTRICT_HEAD, HASH)
    return store


def officer(store, username):
    row = store.get_officer_by_username(username)
    assert row is not None, username
    return row


def assigned(store, cid):
    row = store.get_complaint(cid)
    return store.get_officer(row["assigned_officer_id"]) if row["assigned_officer_id"] else None


# Routing and time limits

def test_every_charter_type_has_a_field():
    for key in CHARTER["complaint_types"]:
        assert key in FIELD_FOR_TYPE, key


def test_leak_goes_to_water_depot_with_charter_deadline(portal, staffed):
    view = portal.register("Ravi Kumar", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    assert view["field"] == "Water supply"
    assert view["deadline"] == iso(NOW + timedelta(days=3))
    officer_row = assigned(staffed, view["id"])
    assert officer_row["field"] == "water"
    assert officer_row["level"] == DEPOT
    assert view["assigned_to"] == officer_row["name"]


def test_billing_and_new_connection_go_to_their_fields(portal, staffed):
    assert portal.register("Asha", CONTACT, BILL, ward_number=WARD, use_llm=False, now=NOW)["field"] == "Billing and charges"
    assert portal.register("Asha", CONTACT, NEW_CONN, ward_number=WARD, use_llm=False, now=NOW)["field"] == "New connections"


@pytest.mark.parametrize("name, contact, text", [
    ("A", CONTACT, LEAK),
    ("Ravi", "12345", LEAK),
    ("Ravi", CONTACT, "too short"),
])
def test_register_rejects_bad_input(portal, staffed, name, contact, text):
    with pytest.raises(PortalError) as raised:
        portal.register(name, contact, text, ward_number=WARD, use_llm=False, now=NOW)
    assert raised.value.status == 400


def test_complaint_with_no_officer_waits_and_says_so(store, portal):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    assert view["assigned_to"] == "Waiting for an officer to be assigned"
    kinds = [event["kind"] for event in store.get_events(view["id"])]
    assert "unassigned" in kinds


def test_overdue_moves_complaint_to_next_level(store, portal, staffed):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    assert portal.check_overdue(NOW + timedelta(days=2)) == []  # still inside the 3-day limit

    moved = portal.check_overdue(NOW + timedelta(days=4))
    assert view["id"] in moved
    row = store.get_complaint(view["id"])
    assert row["stage"] == "deputy_ae"
    assert row["stage_deadline"] == iso(NOW + timedelta(days=4) + timedelta(days=2))
    assert assigned(store, view["id"])["username"] == "water.deputy_ae"


def test_escalation_walks_every_level_to_district_head(store, portal, staffed):
    view = portal.register("Ravi", CONTACT, SEWER, ward_number=WARD, use_llm=False, now=NOW)
    cid = view["id"]
    expected = ["deputy_ae", "area_engineer", "superintendent_engineer", DISTRICT_HEAD]
    when = NOW
    for stage in expected:
        when = when + timedelta(days=10)  # well past every limit
        assert cid in portal.check_overdue(when)
        row = store.get_complaint(cid)
        assert row["stage"] == stage

    row = store.get_complaint(cid)
    assert row["stage_deadline"] is None
    assert assigned(store, cid)["username"] == "district.head"
    assert cid not in portal.check_overdue(when + timedelta(days=100))


def test_stage_path_and_windows_follow_the_charter():
    assert stage_path("sewer_network") == [DEPOT, "deputy_ae", "area_engineer", "superintendent_engineer", DISTRICT_HEAD]
    assert stage_path(None) == [DEPOT, DISTRICT_HEAD]
    assert stage_window(4, None, "sewer_network", DEPOT, CHARTER).days == 4
    assert stage_window(None, None, "water_network", "deputy_ae", CHARTER).days == 2
    assert stage_window(None, None, None, DEPOT, CHARTER) is None


# Resolution and citizen confirmation

def test_resolve_then_citizen_confirms_closes(store, portal, staffed):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    depot = assigned(store, view["id"])
    detail = portal.resolve(depot, view["id"], "Pipe repaired at the junction.", now=NOW + timedelta(hours=5))
    assert detail["status"] == AWAITING
    assert detail["deadline"] is None

    asked = portal.confirm(view["id"], CONTACT, True, "Thank you", now=NOW + timedelta(days=1))
    assert asked["status"] == AWAITING
    assert asked["awaiting_code"] is True
    closed = portal.confirm_code(view["id"], CONTACT, asked["demo_code"], now=NOW + timedelta(days=1))
    assert closed["status"] == CLOSED
    with pytest.raises(PortalError) as raised:
        portal.confirm_code(view["id"], CONTACT, asked["demo_code"], now=NOW + timedelta(days=1))
    assert raised.value.status == 409


def test_citizen_says_not_fixed_goes_to_ward_office_then_district(store, portal, staffed):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    portal.resolve(assigned(store, view["id"]), view["id"], "Clamp fitted.", now=NOW + timedelta(hours=2))
    result = portal.confirm(view["id"], CONTACT, False, "Still leaking at night", now=NOW + timedelta(days=1))
    assert result["status"] == OPEN
    row = store.get_complaint(view["id"])
    assert row["stage"] == "ward"
    assert json.loads(row["stage_path"]) == [DEPOT, "ward", DISTRICT_HEAD]
    assert assigned(store, view["id"])["username"] == "water.depot"
    assert any("Still leaking at night" in event["message"] for event in result["events"])


def test_confirm_only_when_awaiting(store, portal, staffed):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    with pytest.raises(PortalError) as raised:
        portal.confirm(view["id"], CONTACT, True, "", now=NOW)
    assert raised.value.status == 409


def test_only_assigned_officer_can_resolve(store, portal, staffed):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    billing = officer(store, "billing.depot")
    with pytest.raises(PortalError) as wrong_field:
        portal.resolve(billing, view["id"], "Done", now=NOW)
    assert wrong_field.value.status == 404  # not visible to this officer

    head = officer(store, "district.head")
    with pytest.raises(PortalError) as head_error:
        portal.resolve(head, view["id"], "Done", now=NOW)
    assert head_error.value.status == 403  # visible, but not theirs to resolve


def test_resolve_and_notes_need_text(store, portal, staffed):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    depot = assigned(store, view["id"])
    with pytest.raises(PortalError) as empty_resolve:
        portal.resolve(depot, view["id"], "   ", now=NOW)
    assert empty_resolve.value.status == 400
    with pytest.raises(PortalError) as empty_note:
        portal.add_note(depot, view["id"], "", now=NOW)
    assert empty_note.value.status == 400


def test_manual_escalation_stops_at_district_head(store, portal, staffed):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    cid = view["id"]
    for _ in range(4):  # depot -> deputy -> area -> superintendent -> district head
        current = assigned(store, cid)
        portal.escalate(current, cid, "Crew not sent", now=NOW)
    assert store.get_complaint(cid)["stage"] == DISTRICT_HEAD
    with pytest.raises(PortalError) as raised:
        portal.escalate(assigned(store, cid), cid, "Again", now=NOW)
    assert raised.value.status == 409


# Citizen privacy and officer visibility

def test_citizen_needs_the_matching_mobile_number(portal, staffed):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    with pytest.raises(PortalError) as wrong:
        portal.track(view["id"], "9999999999")
    assert wrong.value.status == 404
    assert portal.track(view["id"].lower(), "+91 98765 43210")["id"] == view["id"]


def test_officer_sees_only_assigned_complaints_and_district_head_sees_all(store, portal, staffed):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    ids_for_head = [row["id"] for row in portal.officer_list(officer(store, "district.head"))]
    ids_for_billing = [row["id"] for row in portal.officer_list(officer(store, "billing.depot"))]
    assert view["id"] in ids_for_head
    assert view["id"] not in ids_for_billing
    with pytest.raises(PortalError):
        portal.officer_detail(officer(store, "billing.depot"), view["id"])


def test_officer_detail_shows_route_and_history(store, portal, staffed):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    detail = portal.officer_detail(assigned(store, view["id"]), view["id"], now=NOW)
    assert detail["citizen_contact"] == "9876543210"
    assert detail["can_resolve"] is True
    assert detail["can_escalate"] is True
    assert len(detail["path"]) == 5
    assert any(event["kind"] == "registered" for event in detail["events"])


# Login, passwords, and sessions

def test_password_hash_round_trip():
    stored = hash_password("correct horse")
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong horse", stored)
    assert not verify_password("anything", "not-a-hash")
    assert not verify_password("anything", None)


def test_login_checks_password_and_hides_hash(portal, staffed):
    view = portal.login("water.depot", PASSWORD)
    assert view["level"] == DEPOT
    assert "password_hash" not in view
    with pytest.raises(PortalError) as raised:
        portal.login("water.depot", "wrong-password")
    assert raised.value.status == 401


def test_sessions_expire():
    sessions = Sessions()
    token = sessions.create(5, NOW)
    assert sessions.officer_id(token, NOW + timedelta(hours=1)) == 5
    assert sessions.officer_id(token, NOW + timedelta(hours=9)) is None
    assert sessions.officer_id(None, NOW) is None


def test_seed_creates_each_account_once(store):
    created = seed_demo_officers(store, "demo-password-1")
    assert len(created) == len(FIELDS) * len(LEVELS) + 1
    assert "district.head" in created
    assert seed_demo_officers(store, "demo-password-1") == []


def test_seed_rejects_short_password(store):
    with pytest.raises(ValueError):
        seed_demo_officers(store, "short")


# Web API

@pytest.fixture
def server_url(store, staffed):
    httpd = portal_server.make_server("127.0.0.1", 0, Portal(store), Sessions())
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    yield f"http://{host}:{port}"
    httpd.shutdown()
    httpd.server_close()


def call(base, method, path, payload=None, cookie=None, content_type="application/json",
         cookie_name="portal_session"):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {}
    if data is not None:
        headers["Content-Type"] = content_type
    if cookie:
        headers["Cookie"] = f"{cookie_name}={cookie}"
    request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, _decode(response.read()), response.headers
    except urllib.error.HTTPError as error:
        return error.code, _decode(error.read()), error.headers


def _decode(raw):
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        return raw.decode("utf-8", "replace")


def login_cookie(base, username):
    status, _, headers = call(base, "POST", "/api/officer/login", {"username": username, "password": PASSWORD})
    assert status == 200
    return headers.get("Set-Cookie").split(";")[0].split("=", 1)[1]


def test_pages_are_served(server_url):
    status, body, _ = call(server_url, "GET", "/")
    assert status == 200 and "User Login" in body and "Worker Login" in body and "Officer Login" in body
    status, body, _ = call(server_url, "GET", "/officer")
    assert status == 200 and "Complaints assigned to you" in body


@pytest.mark.parametrize("path, text", [
    ("/home", "Register Complaint"),
    ("/register", "Describe the problem"),
    ("/track", "Track Complaint"),
])
def test_citizen_pages_are_served(server_url, path, text):
    status, body, _ = call(server_url, "GET", path)
    assert status == 200 and text in body
    assert "/assets/portal.js" in body and "/assets/portal.css" in body


def test_track_page_has_the_search_and_progress(server_url):
    status, body, _ = call(server_url, "GET", "/track")
    assert status == 200
    for part in ('id="trackForm"', 'id="stepper"', 'id="rEvents"', 'id="confirmArea"', "/api/track"):
        assert part in body


@pytest.mark.parametrize("path, content_type, text", [
    ("/assets/portal.css", "text/css", "--primary"),
    ("/assets/portal.js", "text/javascript", "window.Portal"),
    ("/assets/icons.svg", "image/svg+xml", 'id="skyline"'),
])
def test_shared_assets_are_served(server_url, path, content_type, text):
    with urllib.request.urlopen(server_url + path, timeout=10) as response:
        assert response.status == 200
        assert response.headers.get_content_type() == content_type
        assert text in response.read().decode("utf-8")


def test_only_listed_assets_are_served(server_url):
    status, _, _ = call(server_url, "GET", "/assets/../server.py")
    assert status == 404
    status, _, _ = call(server_url, "GET", "/assets/missing.css")
    assert status == 404


def test_pages_make_no_outside_requests(server_url):
    """Every page and asset works offline: nothing is loaded from another site."""
    for path in ["/", "/signup", "/home", "/register", "/track", "/officer", "/officer/signup",
                 "/worker", "/worker/signup", "/assets/portal.css", "/assets/portal.js"]:
        with urllib.request.urlopen(server_url + path, timeout=10) as response:
            body = response.read().decode("utf-8")
        body = body.replace("http://www.w3.org/2000/svg", "")  # the SVG namespace name, not a request
        assert "http://" not in body and "https://" not in body, path


def test_pages_use_neutral_branding(server_url):
    """No official name or government footer on any page."""
    for path in ["/", "/signup", "/home", "/register", "/track", "/officer", "/officer/signup", "/worker", "/worker/signup"]:
        with urllib.request.urlopen(server_url + path, timeout=10) as response:
            body = response.read().decode("utf-8")
        assert "Chennai Kural" not in body, path
        assert "Government of Tamil Nadu" not in body, path
        assert "Not affiliated with CMWSSB" in body, path
        assert "Made by Abhinav Reddy and Tony Madhuri." in body, path


def citizen_cookie(base, name="Ravi Kumar", contact=CONTACT, address=ADDRESS, ward=WARD):
    """Sign a citizen up (once), then log in over HTTP with a code. Return the session cookie."""
    call(base, "POST", "/api/citizen/signup",
         {"name": name, "contact": contact, "address": address, "ward_number": ward})
    status, body, _ = call(base, "POST", "/api/citizen/login", {"contact": contact})
    assert status == 200
    status, _, headers = call(base, "POST", "/api/citizen/verify", {"contact": contact, "code": body["code"]})
    assert status == 200
    return headers.get("Set-Cookie").split(";")[0].split("=", 1)[1]


def test_citizen_flow_over_http(server_url):
    citizen = citizen_cookie(server_url)
    status, body, _ = call(server_url, "POST", "/api/complaints", {"complaint": LEAK, "use_llm": False},
                           cookie=citizen, cookie_name="citizen_session")
    assert status == 201
    cid = body["id"]
    assert body["ward"] == "Ward 115"

    status, _, _ = call(server_url, "POST", "/api/track", {"id": cid, "contact": "9999999999"})
    assert status == 404

    status, body, _ = call(server_url, "POST", "/api/track", {"id": cid, "contact": CONTACT})
    assert status == 200
    assert body["status"] == OPEN


def test_officer_resolves_and_citizen_confirms_over_http(server_url):
    citizen = citizen_cookie(server_url)
    _, created, _ = call(server_url, "POST", "/api/complaints", {"complaint": LEAK, "use_llm": False},
                         cookie=citizen, cookie_name="citizen_session")
    cid = created["id"]
    cookie = login_cookie(server_url, "water.depot")

    status, body, _ = call(server_url, "GET", "/api/officer/complaints", cookie=cookie)
    assert status == 200
    assert cid in [item["id"] for item in body["complaints"]]

    status, body, _ = call(server_url, "POST", f"/api/officer/complaints/{cid}/resolve",
                           {"note": "Repaired the service line."}, cookie=cookie)
    assert status == 200 and body["status"] == AWAITING

    status, body, _ = call(server_url, "POST", "/api/confirm", {"id": cid, "contact": CONTACT, "fixed": True})
    assert status == 200 and body["status"] == AWAITING and body["demo_code"]

    status, body, _ = call(server_url, "POST", "/api/confirm-code",
                           {"id": cid, "contact": CONTACT, "code": "000000"})
    assert status == 400 and "does not match" in body["error"]

    status, body, _ = call(server_url, "POST", "/api/confirm", {"id": cid, "contact": CONTACT, "fixed": True})
    status, body, _ = call(server_url, "POST", "/api/confirm-code",
                           {"id": cid, "contact": CONTACT, "code": body["demo_code"]})
    assert status == 200 and body["status"] == CLOSED


def test_officer_routes_need_login(server_url):
    status, _, _ = call(server_url, "GET", "/api/officer/complaints")
    assert status == 401


def test_bad_login_is_refused(server_url):
    status, body, _ = call(server_url, "POST", "/api/officer/login", {"username": "water.depot", "password": "nope"})
    assert status == 401
    assert "Wrong username or password" in body["error"]


def test_json_is_required_for_posts(server_url):
    status, _, _ = call(server_url, "POST", "/api/complaints", "name=Ravi", content_type="text/plain")
    assert status == 415


def test_only_district_head_can_run_overdue_check(server_url):
    water_cookie = login_cookie(server_url, "water.depot")
    status, _, _ = call(server_url, "POST", "/api/officer/check-overdue", {}, cookie=water_cookie)
    assert status == 403
    head_cookie = login_cookie(server_url, "district.head")
    status, body, _ = call(server_url, "POST", "/api/officer/check-overdue", {}, cookie=head_cookie)
    assert status == 200 and "escalated" in body


def test_logout_ends_the_session(server_url):
    cookie = login_cookie(server_url, "water.depot")
    assert call(server_url, "GET", "/api/officer/me", cookie=cookie)[0] == 200
    call(server_url, "POST", "/api/officer/logout", {}, cookie=cookie)
    assert call(server_url, "GET", "/api/officer/me", cookie=cookie)[0] == 401


def test_unknown_path_is_404(server_url):
    assert call(server_url, "GET", "/nothing-here")[0] == 404
    assert call(server_url, "POST", "/api/nothing", {})[0] == 404
