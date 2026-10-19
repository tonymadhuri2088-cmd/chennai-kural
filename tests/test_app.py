"""Tests for the LLM classifier, the end-to-end pipeline, and the local web app.

None of these tests need Ollama. The LLM path is tested with a fake answer, and the
"Ollama not running" path is tested against a port that is closed.
"""

import json
import socket
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "complaint_tools"))
sys.path.insert(0, str(ROOT / "app"))

# pylint: disable=wrong-import-position
from complaintrouter import llm_classify  # noqa: E402
from complaintrouter.common import load_charter  # noqa: E402
from complaintrouter.llm_classify import classify, parse_llm_answer  # noqa: E402
from complaintrouter.pipeline import run_complaint  # noqa: E402
from complaintrouter.reply import BANNER  # noqa: E402
import server as app_server  # noqa: E402

CHARTER = load_charter()
LEAK = "Water is leaking from the pipe near my house for three days, please fix it."
SEWER = "Sewer main is blocked, manhole overflowing on our street, no action in 10 days"


def closed_port_url() -> str:
    """Return a localhost address with nothing listening on it."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"


FAKE_SETTINGS = {"base_url": "http://127.0.0.1:1", "model": "llama3.1", "timeout": 1}


def post_json(url, payload):
    """POST JSON and return (status, decoded body) for both success and error replies."""
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


@pytest.fixture
def server_url():
    httpd = app_server.make_server("127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    yield f"http://{host}:{port}"
    httpd.shutdown()
    httpd.server_close()


# Parsing the model's answer

def test_parse_accepts_valid_choice():
    raw = '{"complaint_type": "water_leakage", "subtype": "distribution_main"}'
    assert parse_llm_answer(raw, CHARTER) == {"complaint_type": "water_leakage", "subtype": "distribution_main"}


def test_parse_finds_json_inside_extra_text():
    raw = 'Sure. {"complaint_type": "sewer_main_blockage", "subtype": null} Done.'
    assert parse_llm_answer(raw, CHARTER) == {"complaint_type": "sewer_main_blockage", "subtype": None}


def test_parse_rejects_unknown_type():
    assert parse_llm_answer('{"complaint_type": "road_repair", "subtype": null}', CHARTER) is None


def test_parse_rejects_non_string_type():
    assert parse_llm_answer('{"complaint_type": ["water_leakage"]}', CHARTER) is None


def test_parse_rejects_text_without_json():
    assert parse_llm_answer("no json here", CHARTER) is None
    assert parse_llm_answer('{"complaint_type": "water_leakage"', CHARTER) is None
    assert parse_llm_answer(None, CHARTER) is None


def test_parse_drops_invalid_subtype():
    raw = '{"complaint_type": "water_leakage", "subtype": "roof"}'
    assert parse_llm_answer(raw, CHARTER) == {"complaint_type": "water_leakage", "subtype": None}


# Classifier behaviour

def test_unreachable_ollama_falls_back_to_keyword():
    settings = {"base_url": closed_port_url(), "model": "llama3.1", "timeout": 2}
    result = classify(LEAK, use_llm=True, settings=settings)
    assert result["classifier"] == "keyword"
    assert result["complaint_type"] == "water_leakage"
    assert "not reachable" in result["llm_status"]


def test_use_llm_false_skips_the_model(monkeypatch):
    def must_not_run(*args, **kwargs):
        raise AssertionError("the model should not be called")

    monkeypatch.setattr(llm_classify, "ask_ollama", must_not_run)
    result = classify(LEAK, use_llm=False)
    assert result["classifier"] == "keyword"
    assert "Not requested" in result["llm_status"]


def test_llm_choice_is_used_and_noted(monkeypatch):
    monkeypatch.setattr(llm_classify, "ask_ollama",
                        lambda prompt, settings: '{"complaint_type": "sewer_main_blockage", "subtype": null}')
    result = classify(SEWER, use_llm=True, settings=FAKE_SETTINGS)
    assert result["classifier"] == "llm"
    assert result["complaint_type"] == "sewer_main_blockage"
    assert any("chosen by the local LLM" in note for note in result["notes"])


def test_llm_cannot_lower_urgency(monkeypatch):
    monkeypatch.setattr(llm_classify, "ask_ollama",
                        lambda prompt, settings: '{"complaint_type": "water_pollution", "subtype": "identified_point"}')
    result = classify("Dirty water, a child is sick in the hospital", use_llm=True, settings=FAKE_SETTINGS)
    assert result["urgent"] is True


def test_llm_missing_subtype_defaults_with_note(monkeypatch):
    monkeypatch.setattr(llm_classify, "ask_ollama",
                        lambda prompt, settings: '{"complaint_type": "water_leakage", "subtype": null}')
    result = classify("Water is leaking from the pipe near my house", use_llm=True, settings=FAKE_SETTINGS)
    assert result["subtype"] == "service_line"
    assert any("defaulted to service_line" in note for note in result["notes"])


def test_llm_disagreeing_with_keywords_is_noted(monkeypatch):
    monkeypatch.setattr(llm_classify, "ask_ollama",
                        lambda prompt, settings: '{"complaint_type": "no_water_supply", "subtype": null}')
    result = classify(LEAK, use_llm=True, settings=FAKE_SETTINGS)
    assert result["complaint_type"] == "no_water_supply"
    assert any("keyword classifier chose" in note for note in result["notes"])


def test_invalid_llm_answer_falls_back_to_keyword(monkeypatch):
    monkeypatch.setattr(llm_classify, "ask_ollama", lambda prompt, settings: "I think it is a road problem")
    result = classify(LEAK, use_llm=True, settings=FAKE_SETTINGS)
    assert result["classifier"] == "keyword"
    assert "not a valid charter type" in result["llm_status"]


# Pipeline: the reply text comes from the tools

def test_pipeline_reply_is_tool_text():
    result = run_complaint(LEAK, None, use_llm=False)
    reply = result["reply"]
    assert reply.startswith(BANNER)
    assert "Complaint reference: (reference to be assigned)" in reply
    assert "Charter timeline for repair: 3 days" in reply
    assert "Note: Shown in the PDF copy (p. 4, section C)." in reply
    assert "Open items for the reviewer:" in reply


def test_pipeline_reports_passed_timeline():
    result = run_complaint(SEWER, 10, use_llm=False)
    assert "has passed (10 days since registration)" in result["reply"]
    assert result["escalation"]["applies"] is True
    assert result["escalation"]["current_level_stated"] is False


def test_pipeline_still_replies_when_ollama_is_down():
    result = run_complaint(LEAK, None, use_llm=True, settings={
        "base_url": closed_port_url(), "model": "llama3.1", "timeout": 2})
    assert result["classification"]["classifier"] == "keyword"
    assert BANNER in result["reply"]


def test_pipeline_unclassified_complaint_is_routed_to_review():
    result = run_complaint("The weather is nice today", None, use_llm=False)
    assert result["classification"]["complaint_type"] == "unclassified"
    assert "Charter timeline for repair: none stated" in result["reply"]
    assert result["route"]["owner"] is None


# Request checking

def test_parse_request_accepts_valid_input():
    params, error = app_server.parse_request({"complaint": " Leak ", "days_elapsed": "3", "use_llm": False})
    assert error is None
    assert params == {"complaint": "Leak", "days_elapsed": 3.0, "use_llm": False}


@pytest.mark.parametrize("payload", [
    "not an object",
    {"complaint": ""},
    {"complaint": "x" * 2001},
    {"complaint": "leak", "days_elapsed": -1},
    {"complaint": "leak", "days_elapsed": 99999},
    {"complaint": "leak", "days_elapsed": True},
    {"complaint": "leak", "days_elapsed": "many"},
    {"complaint": "leak", "use_llm": "yes"},
])
def test_parse_request_rejects_bad_input(payload):
    params, error = app_server.parse_request(payload)
    assert params is None
    assert error


# Web app

def test_index_page_is_served(server_url):
    with urllib.request.urlopen(server_url + "/", timeout=10) as response:
        body = response.read().decode("utf-8")
        assert response.status == 200
        assert "text/html" in response.headers["Content-Type"]
    assert "Draft reply" in body
    assert "http://" not in body and "https://" not in body  # no external resources, works offline


def test_route_endpoint_returns_tool_reply(server_url):
    status, body = post_json(server_url + "/api/route", {"complaint": LEAK, "use_llm": False})
    assert status == 200
    assert body["reply"].startswith(BANNER)
    assert body["classification"]["classifier"] == "keyword"
    assert body["timeline"]["fix_days"] == 3


def test_route_endpoint_reports_ollama_down(server_url, monkeypatch):
    monkeypatch.setenv("COMPLAINTROUTER_OLLAMA_URL", closed_port_url())
    status, body = post_json(server_url + "/api/route", {"complaint": LEAK, "use_llm": True})
    assert status == 200
    assert body["classification"]["classifier"] == "keyword"
    assert "not reachable" in body["classification"]["llm_status"]


def test_route_endpoint_rejects_bad_input(server_url):
    status, body = post_json(server_url + "/api/route", {"complaint": "   "})
    assert status == 400
    assert "Type the complaint" in body["error"]


def test_unknown_path_is_404(server_url):
    status, body = post_json(server_url + "/nope", {"complaint": LEAK})
    assert status == 404
