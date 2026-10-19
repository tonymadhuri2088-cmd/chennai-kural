"""Tests for serving the built Flutter app from /app/, and for the citizen steps the app uses.

No Flutter SDK is needed. The built web folder is faked with a couple of files in a temporary folder.
No LLM or internet is needed: complaints are filed with the keyword classifier (use_llm is false).
"""

import http.client
import importlib.util
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "complaint_tools"))

# pylint: disable=wrong-import-position
from complaint_portal.auth import Sessions  # noqa: E402
from complaint_portal.store import Store  # noqa: E402
from complaint_portal.workflow import Portal  # noqa: E402

_spec = importlib.util.spec_from_file_location("portal_server", ROOT / "portal" / "server.py")
portal_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(portal_server)

CONTACT = "9876543210"


@pytest.fixture
def site(tmp_path):
    """A running server. Its built web folder is tmp_path/web, which the test may create or leave missing."""
    web = tmp_path / "web"
    httpd = portal_server.make_server("127.0.0.1", 0, Portal(Store(tmp_path / "portal.db")),
                                      Sessions(), Sessions(), web_dir=web)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    yield f"{host}:{port}", web
    httpd.shutdown()
    httpd.server_close()


def get(address, path, cookie=None):
    """A GET that does not follow redirects. Returns (status, headers, body)."""
    connection = http.client.HTTPConnection(address, timeout=10)
    headers = {"Cookie": cookie} if cookie else {}
    connection.request("GET", path, headers=headers)
    response = connection.getresponse()
    body = response.read()
    result = (response.status, response.msg, body)
    connection.close()
    return result


def post_json(address, path, payload, cookie=None):
    """A JSON POST. Returns (status, headers, parsed body) for both successes and errors."""
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


def test_app_says_how_to_build_it_when_the_web_folder_is_missing(site):
    address, _ = site
    status, _, body = get(address, "/app/")
    assert status == 404
    assert b"flutter build web" in body


def test_app_without_a_slash_redirects_to_the_app_folder(site):
    address, _ = site
    status, headers, _ = get(address, "/app")
    assert status == 301
    assert headers["Location"] == "/app/"


def test_app_serves_the_built_files_with_their_types(site):
    address, web = site
    web.mkdir()
    (web / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    (web / "main.dart.js").write_text("console.log('hello');", encoding="utf-8")

    status, headers, body = get(address, "/app/")
    assert status == 200
    assert headers.get_content_type() == "text/html"
    assert b"<title>app</title>" in body

    status, headers, body = get(address, "/app/main.dart.js")
    assert status == 200
    assert headers.get_content_type() in ("text/javascript", "application/javascript")
    assert body == b"console.log('hello');"


def test_app_never_serves_a_file_outside_the_web_folder(site, tmp_path):
    address, web = site
    web.mkdir()
    (web / "index.html").write_text("ok", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("private", encoding="utf-8")

    status, _, body = get(address, "/app/../secret.txt")
    assert status == 404
    assert b"private" not in body


def test_citizen_signs_up_logs_in_and_files_a_complaint_over_http(site):
    address, _ = site
    status, _, body = post_json(address, "/api/citizen/signup", {
        "name": "Test Citizen",
        "contact": CONTACT,
        "address": "12 Main Road, Teynampet",
        "ward_number": 1,
    })
    assert status == 201, body

    status, _, body = post_json(address, "/api/citizen/login", {"contact": CONTACT})
    assert status == 200, body
    code = body["code"]

    status, headers, profile = post_json(address, "/api/citizen/verify", {"contact": CONTACT, "code": code})
    assert status == 200, profile
    cookie = headers.get_all("Set-Cookie")[0].split(";")[0]
    assert cookie.startswith("citizen_session=")

    status, _, me = get(address, "/api/me", cookie=cookie)
    assert status == 200
    assert json.loads(me)["role"] == "citizen"

    status, _, complaint = post_json(address, "/api/complaints", {
        "complaint": "Water is leaking from the pipe near my house for three days.",
        "use_llm": False,
    }, cookie=cookie)
    assert status == 201, complaint
    assert complaint["id"]
    assert complaint["status_text"]


def test_complaint_needs_a_logged_in_citizen(site):
    address, _ = site
    status, _, body = post_json(address, "/api/complaints", {
        "complaint": "Water is leaking from the pipe near my house for three days.",
        "use_llm": False,
    })
    assert status == 401
    assert "Log in" in body["error"]
