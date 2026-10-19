"""Tests for officer sign-up and approval, sessions that end at midnight (India time), and the account API.

No LLM or internet is needed. Times are passed in explicitly, so the midnight rule can be tested
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
from complaint_portal.auth import Sessions, next_midnight_india  # noqa: E402
from complaint_portal.store import Store  # noqa: E402
from complaint_portal.workflow import Portal, PortalError  # noqa: E402

_spec = importlib.util.spec_from_file_location("portal_server", ROOT / "portal" / "server.py")
portal_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(portal_server)

NOW = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)  # 15:30 in India
PASSWORD = "a-long-password-1"
CONTACT = "98765 43210"
OFFICER = {
    "name": "Asha Ravi",
    "employee_id": "EMP-100",
    "position": "Assistant Engineer",
    "email": "asha.ravi@example.org",
    "mobile": "9800000002",
    "username": "asha.depot",
    "password": PASSWORD,
    "field": "water",
    "level": "depot",
    "zone_number": "9",
}


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "portal.db")


@pytest.fixture
def portal(store):
    return Portal(store)


@pytest.fixture
def server_url(store):
    httpd = portal_server.make_server("127.0.0.1", 0, Portal(store), Sessions(), Sessions())
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


def page(base, path):
    request = urllib.request.Request(base + path, method="GET")
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, response.read().decode("utf-8")


# Midnight in India

@pytest.mark.parametrize("moment, midnight", [
    ("2026-10-15T10:00:00+00:00", "2026-10-15T18:30:00+00:00"),  # 15:30 IST: midnight is 8.5 hours away
    ("2026-10-15T18:29:59+00:00", "2026-10-15T18:30:00+00:00"),  # one second before midnight IST
    ("2026-10-15T18:30:00+00:00", "2026-10-16T18:30:00+00:00"),  # exactly midnight IST: the next one is tomorrow
    ("2026-10-15T23:00:00+00:00", "2026-10-16T18:30:00+00:00"),
])
def test_midnight_is_the_next_midnight_in_india(moment, midnight):
    assert next_midnight_india(datetime.fromisoformat(moment)) == datetime.fromisoformat(midnight)


def test_officer_session_ends_at_midnight_india_time():
    sessions = Sessions()
    expires = next_midnight_india(NOW)
    token = sessions.create("officer-1", NOW, expires)
    assert sessions.who(token, expires - timedelta(minutes=1)) == "officer-1"
    assert sessions.who(token, expires) is None


# Officer sign-up

def test_officer_sign_up_is_stored_as_pending(portal, store):
    message = portal.sign_up_officer(dict(OFFICER), now=NOW)
    assert "Log in with your username and password" in message["message"]
    row = store.get_officer_by_username("asha.depot")
    assert row["status"] == "pending"
    assert row["employee_id"] == "EMP-100"
    assert row["position"] == "Assistant Engineer"
    assert row["email"] == "asha.ravi@example.org"
    assert row["zone_number"] == 9


def test_pending_officer_can_log_in_with_the_right_password(portal, store):
    # Officers do not wait for approval: the right username and password are enough.
    portal.sign_up_officer(dict(OFFICER), now=NOW)
    view = portal.login("asha.depot", PASSWORD)
    assert view["name"] == "Asha Ravi"
    assert store.set_officer_status("asha.depot", "approved")


def test_wrong_password_on_a_pending_account_does_not_reveal_the_status(portal):
    portal.sign_up_officer(dict(OFFICER), now=NOW)
    with pytest.raises(PortalError) as raised:
        portal.login("asha.depot", "not-the-password")
    assert raised.value.status == 401
    assert raised.value.message == "Wrong username or password."


def test_unknown_officer_username_says_new_user(portal):
    with pytest.raises(PortalError) as raised:
        portal.login("nobody.here", PASSWORD)
    assert raised.value.status == 404
    assert raised.value.message == "You are new user, please sign up."


def test_officer_sign_up_cannot_ask_for_the_district_head_level(portal):
    with pytest.raises(PortalError) as raised:
        portal.sign_up_officer(dict(OFFICER, level="district_head", field="water"), now=NOW)
    assert raised.value.status == 400


def test_the_same_username_cannot_sign_up_twice(portal):
    portal.sign_up_officer(dict(OFFICER), now=NOW)
    with pytest.raises(PortalError) as raised:
        portal.sign_up_officer(dict(OFFICER), now=NOW)
    assert raised.value.status == 409


@pytest.mark.parametrize("change, message", [
    ({"email": "not-an-email"}, "valid email"),
    ({"password": "short"}, "at least 10 characters"),
    ({"username": "Asha Ravi"}, "lower-case letters"),
    ({"field": "parking"}, "field you work in"),
    ({"level": "chief"}, "Choose your level"),
    ({"zone_number": "99"}, "zone from 1 to 15"),
    ({"mobile": "12345"}, "10-digit"),
    ({"employee_id": ""}, "employee ID"),
])
def test_officer_sign_up_checks_each_field(portal, change, message):
    with pytest.raises(PortalError) as raised:
        portal.sign_up_officer(dict(OFFICER, **change), now=NOW)
    assert raised.value.status == 400
    assert message in raised.value.message


def test_officer_sign_up_allows_all_zones(portal, store):
    portal.sign_up_officer(dict(OFFICER, zone_number=""), now=NOW)
    assert store.get_officer_by_username("asha.depot")["zone_number"] is None


def test_approving_an_unknown_username_says_so(store):
    assert store.set_officer_status("nobody.here", "approved") is False


# Officer sign-up and the account API over HTTP

def test_sign_up_pages_are_served(server_url):
    status, body = page(server_url, "/signup")
    assert status == 200 and "User sign-up" in body
    status, body = page(server_url, "/officer/signup")
    assert status == 200 and "Officer sign-up" in body


def test_officer_sign_up_then_login_over_http(server_url):
    status, body, _ = send(server_url, "/api/officer/signup", dict(OFFICER))
    assert status == 201
    assert "must approve" not in body["message"]
    status, body, _ = send(server_url, "/api/officer/login", {"username": "asha.depot", "password": PASSWORD})
    assert status == 200
    assert body["name"] == "Asha Ravi"


def test_approved_officer_logs_in_and_the_session_ends_at_midnight(server_url, store):
    send(server_url, "/api/officer/signup", dict(OFFICER))
    store.set_officer_status("asha.depot", "approved")
    status, body, headers = send(server_url, "/api/officer/login", {"username": "asha.depot", "password": PASSWORD})
    assert status == 200
    cookie_line = headers.get("Set-Cookie")
    max_age = int(cookie_line.split("Max-Age=")[1])
    assert 1 <= max_age <= 86400  # never more than until the next midnight in India
    cookie = cookie_line.split(";")[0]
    status, me, _ = send(server_url, "/api/me", cookie=cookie, method="GET")
    assert status == 200
    assert me["role"] == "officer"
    assert me["name"] == "Asha Ravi"


def test_logout_ends_an_officer_session(server_url, store):
    send(server_url, "/api/officer/signup", dict(OFFICER))
    store.set_officer_status("asha.depot", "approved")
    _, _, headers = send(server_url, "/api/officer/login", {"username": "asha.depot", "password": PASSWORD})
    cookie = headers.get("Set-Cookie").split(";")[0]
    status, _, headers = send(server_url, "/api/logout", {}, cookie=cookie)
    assert status == 200
    assert len(headers.get_all("Set-Cookie")) == 3  # citizen, officer and worker cookies are all cleared
    assert send(server_url, "/api/officer/me", cookie=cookie, method="GET")[0] == 401
    assert send(server_url, "/api/me", cookie=cookie, method="GET")[0] == 401


def test_account_api_says_when_nobody_is_logged_in(server_url):
    status, body, _ = send(server_url, "/api/me", method="GET")
    assert status == 401
    assert body["error"] == "Nobody is logged in."
