"""Complaint portal web server.

Citizens sign up once, then log in with a code to their mobile number and stay logged in until they
log out. Officers sign up for approval, then log in to handle the complaints assigned to them; their
logins end at midnight every day (India time). Anyone can also track a complaint with its ID and
mobile number.
Runs on this computer only (127.0.0.1) unless HOST or --host says otherwise. Uses the Python standard
library, so it needs no extra installs. It also serves the built Flutter app from flutter_app/build/web
under /app/, when that folder exists.

Usage (from the project root):
    python portal/server.py                       then open http://127.0.0.1:8000
    python portal/server.py --port 8080
    HOST=0.0.0.0 PORT=8000 python portal/server.py    listen on every network address (phones, hosting)
    python portal/server.py --check-seconds 60    how often to look for passed time limits

Set up officer accounts first with portal/manage.py (see the README).
"""

import argparse
import json
import mimetypes
import os
import re
import sys
import threading
import time
import traceback
from datetime import timedelta
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "complaint_tools"))

# pylint: disable=wrong-import-position
from complaint_portal.auth import CITIZEN_SESSION_DAYS, Sessions, next_midnight_india  # noqa: E402
from complaint_portal.rules import DISTRICT_HEAD  # noqa: E402
from complaint_portal.store import Store  # noqa: E402
from complaint_portal.workers import WorkerDesk  # noqa: E402
from complaint_portal.sms import load_env_file, sender_from_env  # noqa: E402
from complaint_portal.workflow import Portal, PortalError, utcnow  # noqa: E402

HERE = Path(__file__).resolve().parent
WEB_DIR = ROOT / "flutter_app" / "build" / "web"  # made by: flutter build web --base-href /app/
mimetypes.add_type("application/wasm", ".wasm")
PAGES = {
    "/": HERE / "citizen.html",                 # first screen: User Login and Officer Login
    "/signup": HERE / "signup.html",
    "/home": HERE / "home.html",                # citizen home after login
    "/register": HERE / "register.html",        # Register Complaint form
    "/track": HERE / "track.html",              # Track Complaint (blank for now)
    "/officer": HERE / "officer.html",
    "/officer/signup": HERE / "officer-signup.html",
    "/worker": HERE / "worker.html",                # worker board: complaints to accept, allotted tasks
    "/worker/signup": HERE / "worker-signup.html",
}
# The shared stylesheet, script and icons. Only these files are served from portal/assets.
ASSETS = {
    "/assets/portal.css": (HERE / "assets" / "portal.css", "text/css; charset=utf-8"),
    "/assets/portal.js": (HERE / "assets" / "portal.js", "text/javascript; charset=utf-8"),
    "/assets/icons.svg": (HERE / "assets" / "icons.svg", "image/svg+xml"),
}
COOKIE_NAME = "portal_session"
CITIZEN_COOKIE = "citizen_session"
WORKER_COOKIE = "worker_session"
MAX_BODY_BYTES = 20000
DEFAULT_DB = HERE / "data" / "portal.db"
DEFAULT_CHECK_SECONDS = 30
OFFICER_ACTION = re.compile(r"^/api/officer/complaints/([A-Z0-9-]+)/(resolve|note|escalate)$")
OFFICER_DETAIL = re.compile(r"^/api/officer/complaints/([A-Z0-9-]+)$")
WORKER_ACTION = re.compile(r"^/api/worker/complaints/([A-Za-z0-9-]+)/(accept|request-completion|complete|reject)$")


class Handler(BaseHTTPRequestHandler):
    """Serves the pages, their shared assets and the JSON API. portal and sessions are set by make_server."""

    portal: Portal
    sessions: Sessions
    citizen_sessions: Sessions
    worker_sessions: Sessions
    workers: WorkerDesk
    web_dir: Path

    def do_GET(self):  # noqa: N802 (name required by http.server)
        path = urlsplit(self.path).path
        try:
            if path == "/app":
                self.send_response(301)
                self.send_header("Location", "/app/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path.startswith("/app/"):
                self._send_app_file(path[len("/app/"):])
                return
            if path in PAGES:
                self._send_bytes(200, PAGES[path].read_bytes(), "text/html; charset=utf-8")
                return
            if path in ASSETS:
                asset, content_type = ASSETS[path]
                self._send_bytes(200, asset.read_bytes(), content_type)
                return
            if path == "/api/locations":
                self._send_json(200, self.portal.locations.tree())
                return
            if path == "/api/citizen/me":
                self._send_json(200, self._citizen_profile())
                return
            if path == "/api/citizen/complaints":
                mobile = self._current_citizen()
                self._send_json(200, {"complaints": self.portal.citizen_complaints(mobile)})
                return
            if path == "/api/me":
                self._send_json(200, self._who_am_i())
                return
            if path == "/api/officer/me":
                self._send_json(200, self._officer_view())
                return
            if path == "/api/officer/complaints":
                officer = self._current_officer()
                self._send_json(200, {"complaints": self.portal.officer_list(officer)})
                return
            if path == "/api/officer/notices":
                officer = self._current_officer()
                self._send_json(200, {"notices": self.portal.officer_notices(officer)})
                return
            if path == "/api/worker/me":
                self._send_json(200, self.workers.profile(self._current_worker()))
                return
            if path == "/api/worker/complaints":
                self._send_json(200, self.workers.board(self._current_worker()))
                return
            match = OFFICER_DETAIL.match(path)
            if match:
                officer = self._current_officer()
                self._send_json(200, self.portal.officer_detail(officer, match.group(1)))
                return
            self._send_json(404, {"error": "Not found."})
        except PortalError as error:
            self._send_json(error.status, {"error": error.message})
        except Exception:  # never show internal details to the browser
            traceback.print_exc()
            self._send_json(500, {"error": "Something went wrong on the server."})

    def do_POST(self):  # noqa: N802
        path = urlsplit(self.path).path
        try:
            extra_headers: Dict[str, Any] = {}
            if path == "/api/citizen/match":
                body = self._read_json()
                self._send_json(200, self.portal.match_address(body.get("address")))
                return
            if path == "/api/citizen/signup":
                body = self._read_json()
                view = self.portal.sign_up_citizen(
                    body.get("name"), body.get("contact"), body.get("address"), body.get("ward_number"))
                self._send_json(201, view)
                return
            if path == "/api/citizen/login":
                body = self._read_json()
                self._send_json(200, self.portal.start_citizen_login(body.get("contact")))
                return
            if path == "/api/citizen/verify":
                body = self._read_json()
                profile = self.portal.verify_login(body.get("contact"), body.get("code"))
                now = utcnow()
                expires = now + timedelta(days=CITIZEN_SESSION_DAYS)
                token = self.citizen_sessions.create(profile["mobile"], now, expires)
                extra_headers["Set-Cookie"] = _cookie(token, max_age=CITIZEN_SESSION_DAYS * 86400, name=CITIZEN_COOKIE)
                self._send_json(200, profile, extra_headers)
                return
            if path == "/api/citizen/logout":
                self.citizen_sessions.drop(self._session_token(CITIZEN_COOKIE))
                extra_headers["Set-Cookie"] = _cookie("", max_age=0, name=CITIZEN_COOKIE)
                self._send_json(200, {"ok": True}, extra_headers)
                return
            if path == "/api/logout":
                # Ends whichever session this browser has. Only the logout control shows this.
                self.citizen_sessions.drop(self._session_token(CITIZEN_COOKIE))
                self.sessions.drop(self._session_token())
                self.worker_sessions.drop(self._session_token(WORKER_COOKIE))
                extra_headers["Set-Cookie"] = [
                    _cookie("", max_age=0, name=CITIZEN_COOKIE),
                    _cookie("", max_age=0),
                    _cookie("", max_age=0, name=WORKER_COOKIE),
                ]
                self._send_json(200, {"ok": True}, extra_headers)
                return
            if path == "/api/worker/signup":
                body = self._read_json()
                self._send_json(201, self.workers.sign_up(
                    body.get("name"), body.get("contact"), body.get("address"), body.get("ward_number"),
                    body.get("department")))
                return
            if path == "/api/worker/login":
                body = self._read_json()
                self._send_json(200, self.workers.start_login(body.get("contact")))
                return
            if path == "/api/worker/verify":
                body = self._read_json()
                profile = self.workers.verify_login(body.get("contact"), body.get("code"))
                now = utcnow()
                expires = now + timedelta(days=CITIZEN_SESSION_DAYS)  # workers also stay logged in until they log out
                token = self.worker_sessions.create(profile["mobile"], now, expires)
                extra_headers["Set-Cookie"] = _cookie(token, max_age=CITIZEN_SESSION_DAYS * 86400, name=WORKER_COOKIE)
                self._send_json(200, profile, extra_headers)
                return
            worker_match = WORKER_ACTION.match(path)
            if worker_match:
                mobile = self._current_worker()
                complaint_id, action = worker_match.group(1), worker_match.group(2)
                body = self._read_json()
                if action == "accept":
                    view = self.workers.accept(mobile, complaint_id)
                elif action == "request-completion":
                    view = self.workers.request_completion(mobile, complaint_id)
                elif action == "reject":
                    view = self.workers.reject(mobile, complaint_id, body.get("reason"))
                else:
                    view = self.workers.complete(mobile, complaint_id, body.get("code"))
                self._send_json(200, view)
                return
            if path == "/api/complaints":
                body = self._read_json()
                profile = self.portal.citizen_profile(self._current_citizen())
                # Where the problem is. Older apps do not send it, so the citizen's own address is used then.
                address = body.get("address")
                view = self.portal.register(
                    profile["name"], profile["mobile"], body.get("complaint"),
                    ward_number=profile["ward_number"],
                    use_llm=_flag(body, "use_llm", True),
                    address=profile["address"] if address is None else address,
                    landmark=body.get("landmark"),
                    kind=body.get("kind"), category=body.get("category"), photos=body.get("photos"),
                )
                self._send_json(201, view)
                return
            if path == "/api/track":
                body = self._read_json()
                self._send_json(200, self.portal.track(body.get("id"), body.get("contact")))
                return
            if path == "/api/confirm":
                body = self._read_json()
                view = self.portal.confirm(
                    body.get("id"), body.get("contact"), body.get("fixed"), body.get("comment", ""),
                )
                self._send_json(200, view)
                return
            if path == "/api/confirm-code":
                body = self._read_json()
                view = self.portal.confirm_code(body.get("id"), body.get("contact"), body.get("code"))
                self._send_json(200, view)
                return
            if path == "/api/officer/signup":
                body = self._read_json()
                self._send_json(201, self.portal.sign_up_officer(body))
                return
            if path == "/api/officer/login":
                body = self._read_json()
                officer = self.portal.login(body.get("username"), body.get("password"))
                now = utcnow()
                expires = next_midnight_india(now)  # officer logins end at midnight every day (India time)
                token = self.sessions.create(officer["id"], now, expires)
                max_age = max(1, int((expires - now).total_seconds()))
                extra_headers["Set-Cookie"] = _cookie(token, max_age=max_age)
                self._send_json(200, officer, extra_headers)
                return
            if path == "/api/officer/logout":
                self.sessions.drop(self._session_token())
                extra_headers["Set-Cookie"] = _cookie("", max_age=0)
                self._send_json(200, {"ok": True}, extra_headers)
                return
            if path == "/api/officer/check-overdue":
                officer = self._current_officer()
                if officer["level"] != DISTRICT_HEAD:
                    raise PortalError(403, "Only the District Head Office can run this check.")
                self._send_json(200, {"escalated": self.portal.check_overdue()})
                return

            match = OFFICER_ACTION.match(path)
            if match:
                complaint_id, action = match.group(1), match.group(2)
                officer = self._current_officer()
                body = self._read_json()
                if action == "resolve":
                    view = self.portal.resolve(officer, complaint_id, body.get("note"))
                elif action == "note":
                    view = self.portal.add_note(officer, complaint_id, body.get("note"))
                else:
                    view = self.portal.escalate(officer, complaint_id, body.get("note"))
                self._send_json(200, view)
                return

            self._send_json(404, {"error": "Not found."})
        except PortalError as error:
            self._send_json(error.status, {"error": error.message})
        except Exception:  # never show internal details to the browser
            traceback.print_exc()
            self._send_json(500, {"error": "Something went wrong on the server."})

    # Helpers

    def _send_app_file(self, relative: str) -> None:
        """Serve one file of the built Flutter app. Nothing outside the web folder can be read."""
        web_root = self.web_dir.resolve()
        if not web_root.is_dir():
            self._send_json(404, {"error": "The app has not been built yet. Run flutter build web in the flutter_app folder."})
            return
        target = (web_root / (relative or "index.html")).resolve()
        try:
            target.relative_to(web_root)
        except ValueError:
            self._send_json(404, {"error": "Not found."})
            return
        if not target.is_file():
            self._send_json(404, {"error": "Not found."})
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send_bytes(200, target.read_bytes(), content_type)

    def _read_json(self) -> Dict[str, Any]:
        # Requiring JSON means a plain HTML form on another site cannot send a request here.
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            raise PortalError(415, "Send the request as JSON.")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            raise PortalError(400, "Send a request body.")
        if length > MAX_BODY_BYTES:
            raise PortalError(413, "The request is too large.")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise PortalError(400, "The request is not valid JSON.") from None
        if not isinstance(data, dict):
            raise PortalError(400, "Send a JSON object.")
        return data

    def _session_token(self, name: str = COOKIE_NAME) -> Optional[str]:
        try:
            jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        except cookies.CookieError:
            return None
        morsel = jar.get(name)
        return morsel.value if morsel else None

    def _current_officer(self) -> Dict[str, Any]:
        officer_id = self.sessions.officer_id(self._session_token(), utcnow())
        officer = self.portal.store.get_officer(officer_id) if officer_id is not None else None
        if officer is None:
            raise PortalError(401, "Log in as an officer first.")
        return officer

    def _current_citizen(self) -> str:
        """Return the mobile number of the logged-in citizen. Raise 401 if nobody is logged in."""
        mobile = self.citizen_sessions.who(self._session_token(CITIZEN_COOKIE), utcnow())
        if mobile is None:
            raise PortalError(401, "Log in with your name, mobile number and address first.")
        return mobile

    def _current_worker(self) -> str:
        """Return the mobile number of the logged-in worker. Raise 401 if no worker is logged in."""
        mobile = self.worker_sessions.who(self._session_token(WORKER_COOKIE), utcnow())
        if mobile is None:
            raise PortalError(401, "Log in as a worker first.")
        return mobile

    def _citizen_profile(self) -> Dict[str, Any]:
        return self.portal.citizen_profile(self._current_citizen())

    def _officer_view(self) -> Dict[str, Any]:
        return self.portal.officer_view(self._current_officer())

    def _who_am_i(self) -> Dict[str, Any]:
        """The account behind this browser, for the account panel. Citizens and officers are both checked."""
        mobile = self.citizen_sessions.who(self._session_token(CITIZEN_COOKIE), utcnow())
        if mobile is not None:
            return {"role": "citizen", **self.portal.citizen_profile(mobile)}
        officer_id = self.sessions.officer_id(self._session_token(), utcnow())
        officer = self.portal.store.get_officer(officer_id) if officer_id is not None else None
        if officer is not None:
            return {"role": "officer", **self.portal.officer_view(officer)}
        worker = self.worker_sessions.who(self._session_token(WORKER_COOKIE), utcnow())
        if worker is not None:
            return {"role": "worker", **self.workers.profile(worker)}
        raise PortalError(401, "Nobody is logged in.")

    def _send_json(self, status: int, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> None:
        self._send_bytes(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", headers)

    def _send_bytes(self, status: int, body: bytes, content_type: str, headers: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            # A header can be sent more than once, for example two Set-Cookie lines.
            for item in (value if isinstance(value, list) else [value]):
                self.send_header(name, item)
        self.end_headers()
        self.wfile.write(body)


def _flag(body: Dict[str, Any], key: str, default: bool) -> bool:
    value = body.get(key, default)
    if not isinstance(value, bool):
        raise PortalError(400, f"{key} must be true or false.")
    return value


def _cookie(token: str, max_age: int, name: str = COOKIE_NAME) -> str:
    return f"{name}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"


def make_server(host: str, port: int, portal: Portal, sessions: Sessions,
                citizen_sessions: Optional[Sessions] = None, web_dir: Optional[Path] = None,
                worker_sessions: Optional[Sessions] = None) -> ThreadingHTTPServer:
    """Create the server without starting it. Tests use port 0 to get a free port."""
    bound = type("BoundHandler", (Handler,), {
        "portal": portal,
        "sessions": sessions,
        "citizen_sessions": citizen_sessions or Sessions(),
        "worker_sessions": worker_sessions or Sessions(),
        "workers": WorkerDesk(portal),
        "web_dir": web_dir or WEB_DIR,
    })
    return ThreadingHTTPServer((host, port), bound)


def start_overdue_check(portal: Portal, seconds: float) -> threading.Thread:
    """Look for passed time limits every few minutes, in the background."""

    def run() -> None:
        while True:
            time.sleep(seconds)
            try:
                moved = portal.check_overdue()
                if moved:
                    print(f"Escalated {len(moved)} complaint(s) past their time limit.")
            except Exception:
                traceback.print_exc()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def main() -> None:
    load_env_file(ROOT / ".env")  # SMS settings, if the .env file exists
    parser = argparse.ArgumentParser(description="Run the complaint portal on this computer.")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"),
                        help="Address to listen on (default 127.0.0.1, this computer only; 0.0.0.0 for every address).")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")),
                        help="Port to listen on (default 8000, or the PORT environment variable).")
    parser.add_argument("--db", default=os.environ.get("COMPLAINT_PORTAL_DB", str(DEFAULT_DB)),
                        help="Database file (default portal/data/portal.db).")
    parser.add_argument("--check-seconds", type=float,
                        default=float(os.environ.get("COMPLAINT_PORTAL_CHECK_SECONDS", DEFAULT_CHECK_SECONDS)),
                        help="How often to look for passed time limits (default 30).")
    parser.add_argument("--demo-minutes", type=float,
                        default=float(os.environ.get("COMPLAINT_PORTAL_DEMO_MINUTES", "0")),
                        help="Demo only: make every new time limit this many minutes, to show a time limit passing.")
    args = parser.parse_args()

    sms = sender_from_env()
    portal = Portal(Store(args.db), demo_minutes=args.demo_minutes, sms=sms)
    sessions = Sessions()
    httpd = make_server(args.host, args.port, portal, sessions, Sessions())
    start_overdue_check(portal, args.check_seconds)

    print(f"Complaint portal listening on {args.host}, port {args.port}")
    print(f"Open http://127.0.0.1:{args.port}/ on this computer. Citizens and officers both log in there.")
    print(f"Flutter web app (if built): http://127.0.0.1:{args.port}/app/")
    print(f"Database: {args.db}")
    if sms.configured:
        print(f"Codes are sent by SMS through {sms.name}.")
    else:
        print("SMS is not set up: codes are shown on screen. See .env.example to send them by SMS.")
    if portal.demo_minutes:
        print(f"Demo time limits: every new time limit is {portal.demo_minutes:g} minute(s).")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
