"""Tests for citizen login, address matching, the one-time codes, and the ward-then-district route.

No LLM or internet is needed. Times are passed in explicitly, so codes and time limits can be tested
without waiting.
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
from complaint_portal.auth import CODE_MINUTES, MAX_CODE_TRIES, OneTimeCodes, Sessions, hash_password  # noqa: E402
from complaint_portal.locations import load_locations, match_zones  # noqa: E402
from complaint_portal.rules import (  # noqa: E402
    AWAITING,
    CLOSED,
    DEPOT,
    DISTRICT_HEAD,
    FIELDS,
    WARD as WARD_STAGE,
    path_after_citizen_not_fixed,
    stage_window,
)
from complaint_portal.store import Store  # noqa: E402
from complaint_portal.workflow import Portal, PortalError, iso  # noqa: E402

_spec = importlib.util.spec_from_file_location("portal_server", ROOT / "portal" / "server.py")
portal_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(portal_server)

CHARTER = load_charter()
NOW = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
HASH = hash_password("portal-test-pass")
LEAK = "Water is leaking from the pipe near my house for three days, please fix it."
CONTACT = "98765 43210"
ADDRESS = "14 Pillaiyar Koil Street, Teynampet, Chennai 600018"
WARD = 115  # ward 115 is in zone 9, Teynampet
LEVELS = ["depot", "deputy_ae", "area_engineer", "superintendent_engineer"]


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "portal.db")


@pytest.fixture
def locations():
    return load_locations()


@pytest.fixture
def portal(store, locations):
    return Portal(store, locations)


@pytest.fixture
def staffed(store):
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


def sign_up(portal, now=NOW, name="Ravi Kumar", contact=CONTACT, address=ADDRESS, ward=WARD):
    """Store a citizen's sign-up. Return the message the page shows."""
    return portal.sign_up_citizen(name, contact, address, ward, now=now)


def log_in(portal, now=NOW, contact=CONTACT):
    """Ask for a code for a registered mobile number and enter it. Return the citizen's profile."""
    started = portal.start_citizen_login(contact, now=now)
    return portal.verify_login(contact, started["code"], now=now)


# Matching an address to zones

def test_address_naming_a_zone_points_to_that_zone(locations):
    matches = match_zones("14 Pillaiyar Koil Street, Teynampet, Chennai", locations)
    assert matches[0][0] == 9


def test_zone_name_in_the_address_scores_at_least_three(locations):
    best = match_zones("Ambattur, Chennai", locations)[0]
    assert best[0] == 7
    assert best[1] >= 3


def test_address_with_no_known_name_matches_nothing(locations):
    assert match_zones("12 Some Lane, Unknown Town", locations) == []


def test_match_address_narrows_to_the_matched_zones(portal):
    result = portal.match_address(ADDRESS)
    assert result["matched"] is True
    assert [zone["number"] for zone in result["zones"]] == [9]
    assert "Teynampet zone" in result["note"]


def test_match_address_offers_every_zone_when_nothing_matches(portal):
    result = portal.match_address("12 Some Lane, Unknown Town, Chennai")
    assert result["matched"] is False
    assert len(result["zones"]) == 15


@pytest.mark.parametrize("address", ["", "short", "   "])
def test_match_address_needs_a_detailed_address(portal, address):
    with pytest.raises(PortalError) as raised:
        portal.match_address(address)
    assert raised.value.status == 400


# Citizen sign-up and login

def test_sign_up_then_login_gives_the_saved_details(portal):
    sign_up(portal)
    profile = log_in(portal)
    assert profile["name"] == "Ravi Kumar"
    assert profile["address"] == ADDRESS
    assert profile["zone"] == "Teynampet zone"
    assert profile["ward"] == "Ward 115"
    assert profile["mobile"] == "9876543210"


def test_sign_up_is_stored_in_the_database(portal, store):
    sign_up(portal)
    row = store.get_citizen("9876543210")
    assert row["name"] == "Ravi Kumar"
    assert row["ward_number"] == WARD
    assert row["created_at"] == iso(NOW)


def test_signing_up_twice_with_one_mobile_is_refused(portal):
    sign_up(portal)
    with pytest.raises(PortalError) as raised:
        sign_up(portal, name="Someone Else")
    assert raised.value.status == 409
    assert "Log in with it instead" in raised.value.message


def test_login_does_not_change_the_signed_up_details(portal, store):
    sign_up(portal)
    log_in(portal, now=NOW + timedelta(days=1))
    row = store.get_citizen("9876543210")
    assert row["created_at"] == iso(NOW)
    assert row["updated_at"] == iso(NOW)


def test_sign_up_checks_the_details(portal):
    with pytest.raises(PortalError) as raised:
        sign_up(portal, name="R")
    assert raised.value.status == 400
    with pytest.raises(PortalError) as raised:
        sign_up(portal, contact="12345")
    assert "10-digit" in raised.value.message
    with pytest.raises(PortalError) as raised:
        sign_up(portal, address="short")
    assert "address" in raised.value.message
    with pytest.raises(PortalError) as raised:
        sign_up(portal, ward=999)
    assert "wards 1 to 200" in raised.value.message


def test_unknown_mobile_is_told_to_sign_up(portal):
    with pytest.raises(PortalError) as raised:
        portal.start_citizen_login("9000000009", now=NOW)
    assert raised.value.status == 404
    assert raised.value.message == "You are new user, please sign up."


def test_code_is_six_digits_and_says_how_long_it_lasts(portal):
    sign_up(portal)
    started = portal.start_citizen_login(CONTACT, now=NOW)
    assert len(started["code"]) == 6 and started["code"].isdigit()
    assert started["minutes"] == CODE_MINUTES


def test_verify_without_a_code_asks_for_one(portal):
    sign_up(portal)
    with pytest.raises(PortalError) as raised:
        portal.verify_login(CONTACT, "123456", now=NOW)
    assert "Ask for a code first" in raised.value.message


def test_wrong_code_is_refused(portal):
    sign_up(portal)
    portal.start_citizen_login(CONTACT, now=NOW)
    with pytest.raises(PortalError) as raised:
        portal.verify_login(CONTACT, "000000", now=NOW)
    assert "does not match" in raised.value.message


def test_code_stops_working_after_too_many_wrong_tries(portal):
    sign_up(portal)
    started = portal.start_citizen_login(CONTACT, now=NOW)
    wrong = "000000" if started["code"] != "000000" else "111111"
    for _ in range(MAX_CODE_TRIES):
        with pytest.raises(PortalError):
            portal.verify_login(CONTACT, wrong, now=NOW)
    with pytest.raises(PortalError) as raised:
        portal.verify_login(CONTACT, started["code"], now=NOW)
    assert "Too many wrong codes" in raised.value.message


def test_code_expires(portal):
    sign_up(portal)
    started = portal.start_citizen_login(CONTACT, now=NOW)
    with pytest.raises(PortalError) as raised:
        portal.verify_login(CONTACT, started["code"], now=NOW + timedelta(minutes=CODE_MINUTES + 1))
    assert "expired" in raised.value.message


def test_code_works_only_once(portal):
    sign_up(portal)
    started = portal.start_citizen_login(CONTACT, now=NOW)
    portal.verify_login(CONTACT, started["code"], now=NOW)
    with pytest.raises(PortalError):
        portal.verify_login(CONTACT, started["code"], now=NOW)


def test_a_code_for_one_mobile_does_not_open_another(portal):
    sign_up(portal)
    sign_up(portal, name="Asha", contact="9000000001")
    started = portal.start_citizen_login(CONTACT, now=NOW)
    with pytest.raises(PortalError):
        portal.verify_login("9000000001", started["code"], now=NOW)


def test_citizen_profile_needs_a_login(portal):
    with pytest.raises(PortalError) as raised:
        portal.citizen_profile("9876543210")
    assert raised.value.status == 401


def test_citizen_complaints_show_only_that_citizens_complaints(portal, staffed):
    mine = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    portal.register("Asha", "9000000002", LEAK, ward_number=WARD, use_llm=False, now=NOW)
    listed = [item["id"] for item in portal.citizen_complaints("9876543210", now=NOW)]
    assert listed == [mine["id"]]


# Confirming a fix with a code

def test_fixed_then_wrong_code_keeps_the_complaint_waiting(store, portal, staffed):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    portal.resolve(assigned(store, view["id"]), view["id"], "Repaired.", now=NOW + timedelta(hours=2))
    asked = portal.confirm(view["id"], CONTACT, True, "", now=NOW + timedelta(hours=3))
    wrong = "000000" if asked["demo_code"] != "000000" else "111111"
    with pytest.raises(PortalError):
        portal.confirm_code(view["id"], CONTACT, wrong, now=NOW + timedelta(hours=3))
    assert store.get_complaint(view["id"])["status"] == AWAITING


def test_fixed_code_expires_and_saying_fixed_again_gives_a_new_one(store, portal, staffed):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    portal.resolve(assigned(store, view["id"]), view["id"], "Repaired.", now=NOW + timedelta(hours=2))
    asked = portal.confirm(view["id"], CONTACT, True, "", now=NOW + timedelta(hours=3))
    with pytest.raises(PortalError) as raised:
        portal.confirm_code(view["id"], CONTACT, asked["demo_code"], now=NOW + timedelta(hours=3, minutes=CODE_MINUTES + 1))
    assert "expired" in raised.value.message
    again = portal.confirm(view["id"], CONTACT, True, "", now=NOW + timedelta(hours=4))
    closed = portal.confirm_code(view["id"], CONTACT, again["demo_code"], now=NOW + timedelta(hours=4))
    assert closed["status"] == CLOSED


def test_code_cannot_be_entered_before_saying_fixed(store, portal, staffed):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    portal.resolve(assigned(store, view["id"]), view["id"], "Repaired.", now=NOW + timedelta(hours=2))
    with pytest.raises(PortalError) as raised:
        portal.confirm_code(view["id"], CONTACT, "123456", now=NOW + timedelta(hours=3))
    assert raised.value.status == 409


# Not fixed: ward office, then District Head Office

def test_path_after_not_fixed_goes_through_the_ward_then_district():
    assert path_after_citizen_not_fixed(["depot", "deputy_ae", "district_head"], "deputy_ae") == [
        "depot", "deputy_ae", "ward", "district_head"]
    assert path_after_citizen_not_fixed(["depot", "district_head"], "depot") == [
        "depot", "ward", "district_head"]
    assert path_after_citizen_not_fixed(["depot", "ward", "district_head"], "ward") == [
        "depot", "ward", "district_head"]
    assert path_after_citizen_not_fixed(["depot", "ward", "district_head"], "district_head") == [
        "depot", "ward", "district_head"]


def test_ward_office_has_the_same_time_as_the_depot():
    assert stage_window(3, None, "water_network", WARD_STAGE, CHARTER).days == 3
    assert stage_window(None, 36, None, WARD_STAGE, CHARTER).total_seconds() == 36 * 3600
    assert stage_window(None, None, "water_network", WARD_STAGE, CHARTER) is None


def test_not_fixed_goes_to_the_city_wide_depot_officer_as_ward_office(store, portal, staffed):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    portal.resolve(assigned(store, view["id"]), view["id"], "Clamp fitted.", now=NOW + timedelta(hours=2))
    result = portal.confirm(view["id"], CONTACT, False, "", now=NOW + timedelta(days=1))
    assert result["current_office"] == "Ward office"
    assert assigned(store, view["id"])["username"] == "water.depot"
    assert result["deadline"] == iso(NOW + timedelta(days=4))


def test_not_fixed_goes_to_the_zone_officer_when_one_is_set_up(store, portal, staffed):
    store.insert_officer("water.depot.zone9", "Teynampet water depot", "water", DEPOT, HASH, 9)
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    portal.resolve(assigned(store, view["id"]), view["id"], "Clamp fitted.", now=NOW + timedelta(hours=2))
    portal.confirm(view["id"], CONTACT, False, "", now=NOW + timedelta(days=1))
    assert assigned(store, view["id"])["username"] == "water.depot.zone9"


def test_ward_office_not_fixed_goes_to_district_head(store, portal, staffed):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    portal.resolve(assigned(store, view["id"]), view["id"], "Clamp fitted.", now=NOW + timedelta(hours=2))
    portal.confirm(view["id"], CONTACT, False, "", now=NOW + timedelta(days=1))
    portal.resolve(assigned(store, view["id"]), view["id"], "Pipe replaced.", now=NOW + timedelta(days=2))
    result = portal.confirm(view["id"], CONTACT, False, "", now=NOW + timedelta(days=3))
    assert result["current_office"] == "District Head Office"
    assert assigned(store, view["id"])["username"] == "district.head"
    assert result["deadline"] is None


def test_ward_office_that_runs_out_of_time_passes_it_to_district_head(store, portal, staffed):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    portal.resolve(assigned(store, view["id"]), view["id"], "Clamp fitted.", now=NOW + timedelta(hours=2))
    portal.confirm(view["id"], CONTACT, False, "", now=NOW + timedelta(days=1))
    assert portal.check_overdue(NOW + timedelta(days=3)) == []
    assert view["id"] in portal.check_overdue(NOW + timedelta(days=5))
    row = store.get_complaint(view["id"])
    assert row["stage"] == DISTRICT_HEAD
    assert assigned(store, view["id"])["username"] == "district.head"


def test_district_head_not_fixed_has_nowhere_further_to_go(store, portal, staffed):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=WARD, use_llm=False, now=NOW)
    portal.resolve(assigned(store, view["id"]), view["id"], "Clamp fitted.", now=NOW + timedelta(hours=2))
    portal.confirm(view["id"], CONTACT, False, "", now=NOW + timedelta(days=1))
    portal.resolve(assigned(store, view["id"]), view["id"], "Pipe replaced.", now=NOW + timedelta(days=2))
    portal.confirm(view["id"], CONTACT, False, "", now=NOW + timedelta(days=3))
    portal.resolve(assigned(store, view["id"]), view["id"], "Checked again.", now=NOW + timedelta(days=4))
    result = portal.confirm(view["id"], CONTACT, False, "", now=NOW + timedelta(days=5))
    assert result["current_office"] == "District Head Office"
    kinds = [event["kind"] for event in store.get_events(view["id"])]
    assert "final_level" in kinds


# Web API for citizens

@pytest.fixture
def server_url(staffed):
    httpd = portal_server.make_server("127.0.0.1", 0, Portal(staffed), Sessions(), Sessions())
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    yield f"http://{host}:{port}"
    httpd.shutdown()
    httpd.server_close()


def send(base, path, payload=None, cookie=None, method="POST"):
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    if cookie:
        headers["Cookie"] = cookie
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read()), response.headers
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read()), error.headers


def citizen_login_over_http(base):
    """Sign up if needed, then log in with a code. Return the session cookie and the profile."""
    send(base, "/api/citizen/signup", {
        "name": "Ravi Kumar", "contact": CONTACT, "address": ADDRESS, "ward_number": WARD})
    status, started, _ = send(base, "/api/citizen/login", {"contact": CONTACT})
    assert status == 200
    status, profile, headers = send(base, "/api/citizen/verify", {"contact": CONTACT, "code": started["code"]})
    assert status == 200
    return headers.get("Set-Cookie").split(";")[0], profile


def test_match_endpoint_is_public(server_url):
    status, body, _ = send(server_url, "/api/citizen/match", {"address": ADDRESS})
    assert status == 200
    assert body["matched"] is True
    assert body["zones"][0]["number"] == 9


def test_citizen_me_needs_a_login_and_then_shows_the_profile(server_url):
    assert send(server_url, "/api/citizen/me", method="GET")[0] == 401
    cookie, profile = citizen_login_over_http(server_url)
    assert profile["ward"] == "Ward 115"
    status, body, _ = send(server_url, "/api/citizen/me", cookie=cookie, method="GET")
    assert status == 200
    assert body["address"] == ADDRESS


def test_logged_in_citizen_files_and_sees_the_complaint(server_url):
    cookie, _ = citizen_login_over_http(server_url)
    status, created, _ = send(server_url, "/api/complaints", {"complaint": LEAK, "use_llm": False}, cookie=cookie)
    assert status == 201
    status, body, _ = send(server_url, "/api/citizen/complaints", cookie=cookie, method="GET")
    assert status == 200
    assert [item["id"] for item in body["complaints"]] == [created["id"]]


def test_citizen_confirms_with_the_code_over_http(server_url):
    cookie, _ = citizen_login_over_http(server_url)
    _, created, _ = send(server_url, "/api/complaints", {"complaint": LEAK, "use_llm": False}, cookie=cookie)
    cid = created["id"]
    _, _, officer_headers = send(server_url, "/api/officer/login",
                                 {"username": "water.depot", "password": "portal-test-pass"})
    officer_cookie = officer_headers.get("Set-Cookie").split(";")[0]
    status, _, _ = send(server_url, f"/api/officer/complaints/{cid}/resolve",
                        {"note": "Repaired the service line."}, cookie=officer_cookie)
    assert status == 200

    status, asked, _ = send(server_url, "/api/confirm", {"id": cid, "contact": CONTACT, "fixed": True})
    assert status == 200 and asked["awaiting_code"] is True and asked["demo_code"]

    status, _, _ = send(server_url, "/api/confirm-code", {"id": cid, "contact": CONTACT, "code": "not-a-code"})
    assert status == 400

    status, closed, _ = send(server_url, "/api/confirm-code",
                             {"id": cid, "contact": CONTACT, "code": asked["demo_code"]})
    assert status == 200 and closed["status"] == CLOSED


def test_logout_ends_the_citizen_session(server_url):
    cookie, _ = citizen_login_over_http(server_url)
    assert send(server_url, "/api/citizen/me", cookie=cookie, method="GET")[0] == 200
    send(server_url, "/api/citizen/logout", {}, cookie=cookie)
    assert send(server_url, "/api/citizen/me", cookie=cookie, method="GET")[0] == 401


def test_unknown_mobile_over_http_is_told_to_sign_up(server_url):
    status, body, _ = send(server_url, "/api/citizen/login", {"contact": "9000000009"})
    assert status == 404
    assert body["error"] == "You are new user, please sign up."


def test_sign_up_over_http_does_not_log_in(server_url):
    status, body, headers = send(server_url, "/api/citizen/signup", {
        "name": "Ravi Kumar", "contact": CONTACT, "address": ADDRESS, "ward_number": WARD})
    assert status == 201
    assert "Log in with your mobile number" in body["message"]
    assert headers.get("Set-Cookie") is None
    assert send(server_url, "/api/citizen/me", method="GET")[0] == 401


def test_login_session_lasts_until_logout_not_eight_hours(server_url):
    send(server_url, "/api/citizen/signup", {
        "name": "Ravi Kumar", "contact": CONTACT, "address": ADDRESS, "ward_number": WARD})
    _, started, _ = send(server_url, "/api/citizen/login", {"contact": CONTACT})
    _, _, headers = send(server_url, "/api/citizen/verify", {"contact": CONTACT, "code": started["code"]})
    cookie_line = headers.get("Set-Cookie")
    max_age = int(cookie_line.split("Max-Age=")[1])
    assert max_age > 8 * 3600
    assert max_age <= 366 * 86400


def test_logout_clears_the_session_cookie(server_url):
    cookie, _ = citizen_login_over_http(server_url)
    status, _, headers = send(server_url, "/api/logout", {}, cookie=cookie)
    assert status == 200
    assert "Max-Age=0" in headers.get_all("Set-Cookie")[0]
    assert send(server_url, "/api/me", cookie=cookie, method="GET")[0] == 401


def test_me_reports_the_citizen_role(server_url):
    cookie, _ = citizen_login_over_http(server_url)
    status, body, _ = send(server_url, "/api/me", cookie=cookie, method="GET")
    assert status == 200
    assert body["role"] == "citizen"
    assert body["name"] == "Ravi Kumar"
    assert body["zone"] == "Teynampet zone"


def test_json_is_required_for_citizen_posts(server_url):
    request = urllib.request.Request(server_url + "/api/citizen/login", data=b"contact=9876543210",
                                     headers={"Content-Type": "text/plain"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as raised:
        urllib.request.urlopen(request, timeout=10)
    assert raised.value.code == 415


def test_one_time_codes_are_bound_to_their_key():
    codes = OneTimeCodes()
    code = codes.issue("login:1", NOW)
    assert codes.check("login:2", code, NOW)[0] == "none"
    assert codes.check("login:1", code, NOW)[0] == "ok"
