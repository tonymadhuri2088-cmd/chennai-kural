"""Local web app for the complaint router.

Runs on this computer only (127.0.0.1). Uses the Python standard library for the web
server, so it needs no extra installs beyond requirements.txt.

Usage (from the project root):
    python app/server.py              then open http://127.0.0.1:8000
    python app/server.py --port 8080

The local LLM is used for classification when the box is ticked. Ollama must be running
with the model pulled (ollama pull llama3.1). If it is not reachable, the keyword
classifier is used and the page says so.
"""

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "complaint_tools"))

# pylint: disable=wrong-import-position
from complaintrouter.llm_classify import ollama_settings  # noqa: E402
from complaintrouter.pipeline import run_complaint  # noqa: E402

INDEX_PAGE = Path(__file__).resolve().parent / "index.html"
MAX_COMPLAINT_CHARS = 2000
MAX_DAYS = 3650
MAX_BODY_BYTES = 20000


def parse_request(data: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Check the JSON the page sends. Return (values, None) or (None, error message)."""
    if not isinstance(data, dict):
        return None, "Send a JSON object."

    complaint = data.get("complaint")
    if not isinstance(complaint, str) or not complaint.strip():
        return None, "Type the complaint text."
    if len(complaint) > MAX_COMPLAINT_CHARS:
        return None, f"The complaint is longer than {MAX_COMPLAINT_CHARS} characters."

    days = data.get("days_elapsed")
    if days in (None, ""):
        days = None
    else:
        if isinstance(days, bool):
            return None, "Days elapsed must be a number."
        if isinstance(days, str):
            try:
                days = float(days)
            except ValueError:
                return None, "Days elapsed must be a number."
        if not isinstance(days, (int, float)) or days != days:  # days != days catches NaN
            return None, "Days elapsed must be a number."
        if days < 0 or days > MAX_DAYS:
            return None, f"Days elapsed must be between 0 and {MAX_DAYS}."

    use_llm = data.get("use_llm", True)
    if not isinstance(use_llm, bool):
        return None, "use_llm must be true or false."

    return {"complaint": complaint.strip(), "days_elapsed": days, "use_llm": use_llm}, None


class Handler(BaseHTTPRequestHandler):
    """Serves the page and the one routing endpoint."""

    def do_GET(self):  # noqa: N802 (name required by http.server)
        if urlsplit(self.path).path in ("/", "/index.html"):
            self._send(200, INDEX_PAGE.read_bytes(), "text/html; charset=utf-8")
        else:
            self._send_json(404, {"error": "Not found."})

    def do_POST(self):  # noqa: N802
        if urlsplit(self.path).path != "/api/route":
            self._send_json(404, {"error": "Not found."})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY_BYTES:
            self._send_json(400, {"error": "Send a JSON body of up to 20000 bytes."})
            return

        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_json(400, {"error": "The body is not valid JSON."})
            return

        params, error = parse_request(data)
        if error:
            self._send_json(400, {"error": error})
            return

        result = run_complaint(params["complaint"], params["days_elapsed"], use_llm=params["use_llm"])
        self._send_json(200, result)

    def _send_json(self, status: int, payload: Dict[str, Any]):
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def _send(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def make_server(host: str, port: int) -> ThreadingHTTPServer:
    """Create the server without starting it. Tests use port 0 to get a free port."""
    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description="Run the complaint router web app on this computer.")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default 8000).")
    args = parser.parse_args()

    httpd = make_server("127.0.0.1", args.port)
    settings = ollama_settings()
    print(f"Complaint router running at http://127.0.0.1:{args.port}")
    print(f"Local LLM: {settings['model']} at {settings['base_url']} (used when the box is ticked)")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
