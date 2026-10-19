"""Tests for sending the one-time codes by SMS. No internet is used: the providers get a fake transport."""

import json
import os
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "complaint_tools"))

# pylint: disable=wrong-import-position
from complaint_portal.seed import seed_demo_officers  # noqa: E402
from complaint_portal.sms import (  # noqa: E402
    Fast2Sms, NoSms, TwilioSms, load_env_file, message_text, sender_from_env,
)
from complaint_portal.store import Store  # noqa: E402
from complaint_portal.workers import WorkerDesk  # noqa: E402
from complaint_portal.workflow import Portal  # noqa: E402

NOW = datetime(2026, 10, 18, 4, 0, tzinfo=timezone.utc)
CITIZEN = "9876543210"
WORKER = "9000000001"
HOME = "12 Main Road, Teynampet, Chennai"
LEAK = "Water is leaking from the pipe near the bus stop for three days."


class FakeSms:
    """Records what would be sent, and succeeds or fails as told."""

    name = "fake"
    configured = True

    def __init__(self, works=True):
        self.works = works
        self.sent = []

    def send_code(self, mobile, code, minutes, purpose):
        self.sent.append((mobile, code, minutes, purpose))
        return (True, "sent") if self.works else (False, "No balance in the SMS wallet.")


def make_portal(tmp_path, sms=None):
    store = Store(tmp_path / "portal.db")
    seed_demo_officers(store, "a-long-password")
    portal = Portal(store, sms=sms)
    portal.sign_up_citizen("Ravi Kumar", CITIZEN, HOME, 115, now=NOW)
    return portal


def file(portal):
    return portal.register("Ravi Kumar", CITIZEN, LEAK, ward_number=115, use_llm=False, now=NOW,
                           address="Near 4 Bazaar Road, Teynampet", landmark="")


# Choosing a provider

def test_no_settings_means_no_sms():
    assert isinstance(sender_from_env({}), NoSms)
    assert isinstance(sender_from_env({"SMS_PROVIDER": "fast2sms", "FAST2SMS_API_KEY": "k"}), NoSms)  # no OTP ID
    assert isinstance(sender_from_env({"SMS_PROVIDER": "twilio", "TWILIO_ACCOUNT_SID": "AC1"}), NoSms)


def test_settings_pick_the_provider():
    fast = sender_from_env({"SMS_PROVIDER": "Fast2SMS", "FAST2SMS_API_KEY": "key", "FAST2SMS_OTP_ID": "123"})
    assert isinstance(fast, Fast2Sms) and fast.configured
    twilio = sender_from_env({"SMS_PROVIDER": "twilio", "TWILIO_ACCOUNT_SID": "AC1",
                              "TWILIO_AUTH_TOKEN": "t", "TWILIO_FROM": "+15550001111"})
    assert isinstance(twilio, TwilioSms) and twilio.configured


def test_env_file_is_read_without_overriding(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nSMS_PROVIDER=fast2sms\nFAST2SMS_API_KEY=\"abc\"\nEMPTY=\n", encoding="utf-8")
    monkeypatch.delenv("SMS_PROVIDER", raising=False)
    monkeypatch.delenv("FAST2SMS_API_KEY", raising=False)
    monkeypatch.setenv("FAST2SMS_OTP_ID", "already-set")
    load_env_file(env)
    assert os.environ["SMS_PROVIDER"] == "fast2sms"
    assert os.environ["FAST2SMS_API_KEY"] == "abc"
    assert os.environ["FAST2SMS_OTP_ID"] == "already-set"
    assert "EMPTY" not in os.environ
    load_env_file(tmp_path / "missing.env")  # a missing file is fine


# The providers' requests

def test_fast2sms_sends_our_code_to_the_otp_api():
    calls = []

    def transport(url, headers, body):
        calls.append((url, headers, json.loads(body)))
        return 200, json.dumps({"return": True, "status_code": 200, "message": "OTP sent successfully"})

    sent, _ = Fast2Sms("KEY", "OTP7", transport).send_code(CITIZEN, "123456", 10, "login")
    assert sent
    url, headers, body = calls[0]
    assert url == "https://www.fast2sms.com/dev/otp/send"
    assert headers["Authorization"] == "KEY"
    assert body == {"mobile": CITIZEN, "otp_id": "OTP7", "otp": "123456", "otp_length": 6, "otp_expiry": 10}


def test_fast2sms_failure_gives_the_reason():
    def transport(url, headers, body):
        return 400, json.dumps({"return": False, "status_code": 400, "message": "Invalid OTP ID"})

    sent, detail = Fast2Sms("KEY", "bad", transport).send_code(CITIZEN, "123456", 10, "login")
    assert not sent and "Invalid OTP ID" in detail

    def offline(url, headers, body):
        raise OSError("no network")

    sent, detail = Fast2Sms("KEY", "OTP7", offline).send_code(CITIZEN, "123456", 10, "login")
    assert not sent and "could not be reached" in detail


def test_twilio_sends_to_plus_91_with_basic_auth():
    calls = []

    def transport(url, headers, body):
        calls.append((url, headers, urllib.parse.parse_qs(body.decode())))
        return 201, json.dumps({"sid": "SM1"})

    sent, _ = TwilioSms("AC1", "secret", "+15550001111", transport).send_code(CITIZEN, "654321", 10, "complete")
    assert sent
    url, headers, form = calls[0]
    assert url == "https://api.twilio.com/2010-04-01/Accounts/AC1/Messages.json"
    assert headers["Authorization"].startswith("Basic ")
    assert form["To"] == ["+919876543210"] and form["From"] == ["+15550001111"]
    assert "654321" in form["Body"][0] and "only if the problem is fixed" in form["Body"][0]


def test_message_text_names_the_purpose():
    assert "login code" in message_text("111111", 10, "login")
    assert "close your" in message_text("111111", 10, "confirm")


# The portal with SMS

def test_without_sms_the_code_is_shown_as_before(tmp_path):
    portal = make_portal(tmp_path)
    sent = portal.start_citizen_login(CITIZEN, now=NOW)
    assert len(sent["code"]) == 6 and sent["sent_by_sms"] is False


def test_login_code_goes_by_sms_and_is_not_shown(tmp_path):
    sms = FakeSms()
    portal = make_portal(tmp_path, sms)
    sent = portal.start_citizen_login(CITIZEN, now=NOW)
    assert "code" not in sent
    assert sent["sent_by_sms"] is True and sent["sent_to"] == "98XXXXXX10"
    mobile, code, minutes, purpose = sms.sent[0]
    assert (mobile, minutes, purpose) == (CITIZEN, 10, "login")
    assert portal.verify_login(CITIZEN, code, now=NOW)["mobile"] == CITIZEN


def test_a_failed_sms_shows_the_code_and_the_reason(tmp_path):
    portal = make_portal(tmp_path, FakeSms(works=False))
    sent = portal.start_citizen_login(CITIZEN, now=NOW)
    assert len(sent["code"]) == 6
    assert "No balance" in sent["note"]


def test_worker_codes_go_by_sms(tmp_path):
    sms = FakeSms()
    portal = make_portal(tmp_path, sms)
    desk = WorkerDesk(portal)
    desk.sign_up("Murugan", WORKER, "5 Lake Street, Teynampet, Chennai", 115, "Water supply", now=NOW)
    assert "code" not in desk.start_login(WORKER, now=NOW)
    assert sms.sent[-1][0] == WORKER

    view = file(portal)
    desk.accept(WORKER, view["id"], now=NOW)
    sent = desk.request_completion(WORKER, view["id"], now=NOW)
    assert sent["sent_by_sms"] is True
    mobile, code, _, purpose = sms.sent[-1]
    assert (mobile, purpose) == (CITIZEN, "complete")
    assert view["id"] not in portal.completion_codes  # not shown on the citizen's screen
    assert desk.complete(WORKER, view["id"], code, now=NOW)["status"] == "closed"


def test_confirmation_code_goes_by_sms(tmp_path):
    sms = FakeSms()
    portal = make_portal(tmp_path, sms)
    view = file(portal)
    portal.store.update_complaint(view["id"], status="awaiting_confirmation")
    answer = portal.confirm(view["id"], CITIZEN, True, now=NOW)
    assert "demo_code" not in answer
    assert "SMS" in answer["code_note"]
    mobile, code, _, purpose = sms.sent[-1]
    assert (mobile, purpose) == (CITIZEN, "confirm")
    assert portal.confirm_code(view["id"], CITIZEN, code, now=NOW)["status"] == "closed"


def test_register_page_has_your_complaints_panel():
    page = (ROOT / "portal" / "register.html").read_text(encoding="utf-8")
    assert "Your complaints" in page and 'id="mineList"' in page
    assert "Not completed" in page and "Completed" in page
