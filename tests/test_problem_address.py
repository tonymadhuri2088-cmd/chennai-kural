"""Tests for the address of the problem (and an optional landmark) on a complaint.

The Register Complaint form asks where the problem is. Older apps do not send it, so the server
then uses the citizen's own address. No LLM or internet is needed.
"""

import importlib.util
import json
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "complaint_tools"))

# pylint: disable=wrong-import-position
from complaint_portal.auth import Sessions  # noqa: E402
from complaint_portal.seed import seed_demo_officers  # noqa: E402
from complaint_portal.store import Store  # noqa: E402
from complaint_portal.workflow import Portal, PortalError  # noqa: E402

_spec = importlib.util.spec_from_file_location("portal_server", ROOT / "portal" / "server.py")
portal_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(portal_server)

NOW = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)
CONTACT = "9876543210"
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
    return Portal(store)


def test_the_problem_address_and_landmark_are_stored_and_shown(portal, store):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=115, use_llm=False, now=NOW,
                           address="  Near 4 Bazaar Road, Teynampet  ", landmark="Opposite the bus stop")
    assert view["problem_address"] == "Near 4 Bazaar Road, Teynampet"
    assert view["landmark"] == "Opposite the bus stop"
    depot = store.get_officer_by_username("water.depot")
    detail = portal.officer_detail(depot, view["id"], now=NOW)
    assert detail["problem_address"] == "Near 4 Bazaar Road, Teynampet"
    assert detail["landmark"] == "Opposite the bus stop"
    listed = portal.citizen_complaints(CONTACT, now=NOW)[0]
    assert listed["problem_address"] == "Near 4 Bazaar Road, Teynampet"


def test_the_citizen_sees_their_own_complaint_text_when_tracking(portal):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=115, use_llm=False, now=NOW,
                           address="Near 4 Bazaar Road, Teynampet")
    assert portal.track(view["id"], CONTACT)["complaint_text"] == LEAK
    with pytest.raises(PortalError):
        portal.track(view["id"], "9000000000")  # someone else's number sees nothing


def test_an_empty_landmark_is_stored_as_none(portal):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=115, use_llm=False, now=NOW,
                           address="Near 4 Bazaar Road, Teynampet", landmark="   ")
    assert view["landmark"] is None


def test_without_an_address_nothing_is_stored(portal):
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=115, use_llm=False, now=NOW)
    assert view["problem_address"] is None


@pytest.mark.parametrize("address", ["", "short", 42, "x" * 301])
def test_a_bad_problem_address_is_refused(portal, address):
    with pytest.raises(PortalError) as raised:
        portal.register("Ravi", CONTACT, LEAK, ward_number=115, use_llm=False, now=NOW, address=address)
    assert raised.value.status == 400
    assert "address of the problem" in raised.value.message


def test_a_long_landmark_is_refused(portal):
    with pytest.raises(PortalError) as raised:
        portal.register("Ravi", CONTACT, LEAK, ward_number=115, use_llm=False, now=NOW,
                        address="Near 4 Bazaar Road, Teynampet", landmark="x" * 101)
    assert raised.value.status == 400
    assert "landmark" in raised.value.message


# Over HTTP

@pytest.fixture
def server(store):
    httpd = portal_server.make_server("127.0.0.1", 0, Portal(store), Sessions(), Sessions())
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    yield f"http://{host}:{port}"
    httpd.shutdown()
    httpd.server_close()


def post(base, path, payload, cookie=None):
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    request = urllib.request.Request(base + path, data=json.dumps(payload).encode("utf-8"),
                                     headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.headers, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, error.headers, json.loads(error.read() or b"{}")


def citizen_cookie(base):
    post(base, "/api/citizen/signup", {"name": "Ravi Kumar", "contact": CONTACT, "address": HOME, "ward_number": 115})
    _, _, sent = post(base, "/api/citizen/login", {"contact": CONTACT})
    _, headers, _ = post(base, "/api/citizen/verify", {"contact": CONTACT, "code": sent["code"]})
    return headers.get_all("Set-Cookie")[0].split(";")[0]


def test_the_form_sends_the_problem_address(server):
    cookie = citizen_cookie(server)
    status, _, view = post(server, "/api/complaints", {
        "complaint": LEAK, "use_llm": False,
        "address": "Near 4 Bazaar Road, Teynampet", "landmark": "Opposite the bus stop",
    }, cookie)
    assert status == 201, view
    assert view["problem_address"] == "Near 4 Bazaar Road, Teynampet"
    assert view["landmark"] == "Opposite the bus stop"


def test_an_older_app_without_the_address_uses_the_citizens_own(server):
    cookie = citizen_cookie(server)
    status, _, view = post(server, "/api/complaints", {"complaint": LEAK, "use_llm": False}, cookie)
    assert status == 201, view
    assert view["problem_address"] == HOME
    assert view["landmark"] is None


def test_an_empty_address_from_the_form_is_refused(server):
    cookie = citizen_cookie(server)
    status, _, body = post(server, "/api/complaints", {"complaint": LEAK, "use_llm": False, "address": ""}, cookie)
    assert status == 400
    assert "address of the problem" in body["error"]


def test_complaints_filed_in_the_same_second_list_the_newest_first(portal):
    first = portal.register("Ravi", CONTACT, LEAK, ward_number=115, use_llm=False, now=NOW)
    second = portal.register("Ravi", CONTACT, "No water has come to our street for three days.",
                             ward_number=115, use_llm=False, now=NOW)
    listed = [item["id"] for item in portal.citizen_complaints(CONTACT, now=NOW)]
    assert listed == [second["id"], first["id"]]
