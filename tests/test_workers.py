"""Tests for field workers (sign-up, login, accepting, completing with the citizen's code) and for the
officers' notices when a complaint passes its time limit. No LLM or internet is needed."""

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
from complaint_portal.auth import Sessions  # noqa: E402
from complaint_portal.seed import seed_demo_officers  # noqa: E402
from complaint_portal.store import Store  # noqa: E402
from complaint_portal.workers import WorkerDesk, mask_mobile  # noqa: E402
from complaint_portal.workflow import Portal, PortalError  # noqa: E402

_spec = importlib.util.spec_from_file_location("portal_server", ROOT / "portal" / "server.py")
portal_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(portal_server)

NOW = datetime(2026, 10, 18, 4, 0, tzinfo=timezone.utc)
CITIZEN = "9876543210"
WORKER = "9000000001"
OTHER_WORKER = "9000000002"
HOME = "12 Main Road, Teynampet, Chennai"
LEAK = "Water is leaking from the pipe near the bus stop for three days."
PASSWORD = "a-long-password"


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / "portal.db")
    seed_demo_officers(store, PASSWORD)
    return store


@pytest.fixture
def portal(store):
    portal = Portal(store)
    portal.sign_up_citizen("Ravi Kumar", CITIZEN, HOME, 115, now=NOW)
    return portal


@pytest.fixture
def desk(portal):
    desk = WorkerDesk(portal)
    desk.sign_up("Murugan", WORKER, "5 Lake Street, Teynampet, Chennai", 115, "Water supply", now=NOW)
    desk.sign_up("Selvi", OTHER_WORKER, "9 Temple Street, Adyar, Chennai", 170, "Sewerage", now=NOW)
    return desk


def file(portal, text=LEAK, now=NOW):
    return portal.register("Ravi Kumar", CITIZEN, text, ward_number=115, use_llm=False, now=now,
                           address="Near 4 Bazaar Road, Teynampet", landmark="Opposite the bus stop")


# Sign-up and login

def test_worker_sign_up_needs_a_department(portal):
    desk = WorkerDesk(portal)
    with pytest.raises(PortalError) as raised:
        desk.sign_up("Murugan", WORKER, "5 Lake Street, Teynampet", 115, " ", now=NOW)
    assert raised.value.status == 400 and "department" in raised.value.message


def test_the_same_worker_cannot_sign_up_twice(desk):
    with pytest.raises(PortalError) as raised:
        desk.sign_up("Murugan", WORKER, "5 Lake Street, Teynampet", 115, "Water supply", now=NOW)
    assert raised.value.status == 409


def test_unknown_worker_number_says_new_user(desk):
    with pytest.raises(PortalError) as raised:
        desk.start_login("9111111111", now=NOW)
    assert raised.value.status == 404
    assert raised.value.message == "You are new user, please sign up."


def test_worker_logs_in_with_a_code(desk):
    code = desk.start_login(WORKER, now=NOW)["code"]
    profile = desk.verify_login(WORKER, code, now=NOW)
    assert profile["name"] == "Murugan" and profile["department"] == "Water supply"
    assert profile["ward"] == "Ward 115"


# Accepting

def test_board_lists_open_complaints_with_the_citizens_details(portal, desk):
    view = file(portal)
    board = desk.board(WORKER, now=NOW)
    card = board["available"][0]
    assert card["id"] == view["id"] and board["mine"] == []
    assert card["citizen"]["mobile"] == CITIZEN
    assert card["citizen"]["address"] == HOME
    assert card["problem_address"] == "Near 4 Bazaar Road, Teynampet"
    assert card["complaint_text"] == LEAK


def test_accepting_allots_it_and_the_citizen_sees_work_in_progress(portal, desk):
    view = file(portal)
    card = desk.accept(WORKER, view["id"], now=NOW)
    assert card["work_status"] == "allotted"
    tracked = portal.track(view["id"], CITIZEN)
    assert tracked["work_status"] == "allotted"
    assert tracked["status_text"] == "Allotted to Murugan (Water supply). Work in progress."
    assert tracked["worker"]["name"] == "Murugan"
    board = desk.board(WORKER, now=NOW)
    assert board["available"] == [] and board["mine"][0]["id"] == view["id"]


def test_two_workers_cannot_accept_the_same_complaint(portal, desk):
    view = file(portal)
    desk.accept(WORKER, view["id"], now=NOW)
    with pytest.raises(PortalError) as raised:
        desk.accept(OTHER_WORKER, view["id"], now=NOW)
    assert raised.value.status == 409


# Completing with the citizen's code

def test_completion_needs_the_code_sent_to_the_citizen(portal, desk):
    # Real time here: the shown code lasts 10 minutes from when it was asked for, and the track call uses the clock.
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(microsecond=0)
    view = file(portal)
    desk.accept(WORKER, view["id"], now=now)
    sent = desk.request_completion(WORKER, view["id"], now=now)
    assert sent["sent_to"] == mask_mobile(CITIZEN) == "98XXXXXX10"
    code = portal.track(view["id"], CITIZEN)["completion_code"]
    assert code and len(code) == 6
    with pytest.raises(PortalError) as raised:
        desk.complete(WORKER, view["id"], "000000" if code != "000000" else "111111", now=now)
    assert "does not match" in raised.value.message
    card = desk.complete(WORKER, view["id"], code, now=now)
    assert card["status"] == "closed" and card["work_status"] == "completed"
    tracked = portal.track(view["id"], CITIZEN)
    assert tracked["status"] == "closed"
    assert tracked["status_text"].startswith("Resolved.")
    assert tracked["completion_code"] is None


def test_only_the_allotted_worker_can_complete(portal, desk):
    view = file(portal)
    desk.accept(WORKER, view["id"], now=NOW)
    with pytest.raises(PortalError) as raised:
        desk.request_completion(OTHER_WORKER, view["id"], now=NOW)
    assert raised.value.status == 403


def test_completing_before_asking_for_a_code_is_refused(portal, desk):
    view = file(portal)
    desk.accept(WORKER, view["id"], now=NOW)
    with pytest.raises(PortalError) as raised:
        desk.complete(WORKER, view["id"], "123456", now=NOW)
    assert raised.value.status == 400


# Notices when a time limit passes

def test_a_passed_time_limit_makes_a_notice_with_the_citizen_and_the_worker(store, desk):
    portal = desk.portal
    view = file(portal)
    desk.accept(WORKER, view["id"], now=NOW)
    depot = store.get_officer_by_username("water.depot")
    later = NOW + timedelta(days=30)
    moved = portal.check_overdue(now=later)
    assert view["id"] in moved
    notices = portal.officer_notices(depot)
    assert len(notices) == 1
    notice = notices[0]
    assert notice["complaint_id"] == view["id"]
    assert notice["department"] == "Water supply"
    assert notice["citizen"]["mobile"] == CITIZEN and notice["citizen"]["name"] == "Ravi Kumar"
    assert notice["worker"]["name"] == "Murugan" and notice["worker"]["mobile"] == WORKER
    assert notice["moved_to"]
    head = store.get_officer_by_username("district.head")
    assert [n["complaint_id"] for n in portal.officer_notices(head)] == [view["id"]]


def test_the_same_passed_time_limit_is_noticed_once(store, desk):
    portal = desk.portal
    view = file(portal)
    head = store.get_officer_by_username("district.head")
    later = NOW + timedelta(days=30)
    portal.check_overdue(now=later)
    portal.check_overdue(now=later)
    assert [n["complaint_id"] for n in portal.officer_notices(head)] == [view["id"]]


def test_each_level_that_passes_its_time_limit_gets_one_notice(store, desk):
    portal = desk.portal
    file(portal)
    head = store.get_officer_by_username("district.head")
    for days in range(1, 400, 5):
        portal.check_overdue(now=NOW + timedelta(days=days))
    offices = [n["office"] for n in portal.officer_notices(head)]
    assert offices and len(offices) == len(set(offices))


def test_demo_minutes_make_short_time_limits(store):
    portal = Portal(store, demo_minutes=2)
    portal.sign_up_citizen("Ravi Kumar", CITIZEN, HOME, 115, now=NOW)
    view = file(portal)
    assert view["deadline"] == (NOW + timedelta(minutes=2)).isoformat()


# Over HTTP

@pytest.fixture
def server(store):
    portal = Portal(store)
    httpd = portal_server.make_server("127.0.0.1", 0, portal, Sessions(), Sessions(), worker_sessions=Sessions())
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    yield f"http://{host}:{port}", portal
    httpd.shutdown()
    httpd.server_close()


def call(base, path, payload=None, cookie=None):
    headers = {}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    if cookie:
        headers["Cookie"] = cookie
    request = urllib.request.Request(base + path, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.headers, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, error.headers, json.loads(error.read() or b"{}")


def test_worker_flow_over_http(server):
    base, portal = server
    portal.sign_up_citizen("Ravi Kumar", CITIZEN, HOME, 115, now=NOW)
    view = file(portal)
    status, _, body = call(base, "/api/worker/signup", {
        "name": "Murugan", "contact": WORKER, "address": "5 Lake Street, Teynampet, Chennai",
        "ward_number": 115, "department": "Water supply"})
    assert status == 201, body
    status, _, sent = call(base, "/api/worker/login", {"contact": WORKER})
    assert status == 200
    status, headers, profile = call(base, "/api/worker/verify", {"contact": WORKER, "code": sent["code"]})
    assert status == 200 and profile["department"] == "Water supply"
    cookie = headers.get_all("Set-Cookie")[0].split(";")[0]
    assert cookie.startswith("worker_session=")
    assert call(base, "/api/me", cookie=cookie)[2]["role"] == "worker"
    status, _, board = call(base, "/api/worker/complaints", cookie=cookie)
    assert status == 200 and board["available"][0]["id"] == view["id"]
    status, _, card = call(base, f"/api/worker/complaints/{view['id']}/accept", {}, cookie)
    assert status == 200 and card["work_status"] == "allotted"
    status, _, sent = call(base, f"/api/worker/complaints/{view['id']}/request-completion", {}, cookie)
    assert status == 200 and sent["sent_to"] == "98XXXXXX10"
    code = portal.track(view["id"], CITIZEN)["completion_code"]
    status, _, card = call(base, f"/api/worker/complaints/{view['id']}/complete", {"code": code}, cookie)
    assert status == 200 and card["status"] == "closed"


def test_worker_pages_need_a_worker_login(server):
    base, _ = server
    status, _, body = call(base, "/api/worker/complaints")
    assert status == 401 and "worker" in body["error"]


def test_officer_notices_over_http(server, store):
    base, portal = server
    portal.sign_up_citizen("Ravi Kumar", CITIZEN, HOME, 115, now=NOW)
    view = file(portal)
    portal.check_overdue(now=NOW + timedelta(days=30))
    status, headers, _ = call(base, "/api/officer/login", {"username": "water.depot", "password": PASSWORD})
    assert status == 200
    cookie = headers.get("Set-Cookie").split(";")[0]
    status, _, body = call(base, "/api/officer/notices", cookie=cookie)
    assert status == 200
    assert [n["complaint_id"] for n in body["notices"]] == [view["id"]]


@pytest.mark.parametrize("path, text", [("/worker", "Allotted tasks"), ("/worker/signup", "Department of work")])
def test_worker_pages_are_served(server, path, text):
    base, _ = server
    with urllib.request.urlopen(base + path, timeout=10) as response:
        body = response.read().decode("utf-8")
    assert text in body
