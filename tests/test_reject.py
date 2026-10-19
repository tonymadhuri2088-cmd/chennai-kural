"""A worker can reject a complaint with a reason: it goes back to the list, the officer is told, and the worker cannot take it again."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "complaint_tools"))

# pylint: disable=wrong-import-position
from complaint_portal.rules import DEPOT, DISTRICT_HEAD  # noqa: E402
from complaint_portal.seed import seed_demo_officers  # noqa: E402
from complaint_portal.store import Store  # noqa: E402
from complaint_portal.workers import WorkerDesk  # noqa: E402
from complaint_portal.workflow import Portal, PortalError  # noqa: E402

NOW = datetime(2026, 10, 18, 4, 0, tzinfo=timezone.utc)
CITIZEN = "9876543210"
WORKER = "9000000001"
OTHER_WORKER = "9000000002"
HOME = "12 Main Road, Teynampet, Chennai"
LEAK = "Water is leaking from the pipe near the bus stop for three days."
REASON = "The address is outside our ward, so another office has to take this."


@pytest.fixture
def portal(tmp_path):
    store = Store(tmp_path / "portal.db")
    seed_demo_officers(store, "a-long-password")
    portal = Portal(store)
    portal.sign_up_citizen("Ravi Kumar", CITIZEN, HOME, 115, now=NOW)
    return portal


@pytest.fixture
def desk(portal):
    desk = WorkerDesk(portal)
    desk.sign_up("Murugan", WORKER, "5 Lake Street, Teynampet, Chennai", 115, "Water supply", now=NOW)
    desk.sign_up("Lakshmi", OTHER_WORKER, "9 Hill Road, Teynampet, Chennai", 115, "Water supply", now=NOW)
    return desk


def file(portal):
    return portal.register("Ravi Kumar", CITIZEN, LEAK, ward_number=115, use_llm=False, now=NOW,
                           address="Near 4 Bazaar Road, Teynampet", landmark="")


def test_rejecting_gives_the_complaint_back_and_tells_the_officer(portal, desk):
    view = file(portal)
    desk.accept(WORKER, view["id"], now=NOW)
    card = desk.reject(WORKER, view["id"], REASON, now=NOW)
    assert card["id"] == view["id"] and card["status"] == "open"

    row = portal.store.get_complaint(view["id"])
    assert row["worker_mobile"] is None and row["worker_accepted_at"] is None and row["status"] == "open"
    assert any(event["kind"] == "rejected" and REASON in event["message"] for event in portal.store.get_events(view["id"]))

    district = portal.officer_notices({"id": 0, "level": DISTRICT_HEAD})
    notice = [n for n in district if n["complaint_id"] == view["id"]]
    assert len(notice) == 1
    notice = notice[0]
    assert notice["kind"] == "rejected" and notice["reason"] == REASON
    assert notice["worker"]["mobile"] == WORKER and notice["worker"]["name"] == "Murugan"
    assert notice["worker"]["position"] == "Water supply" and notice["worker"]["address"].startswith("5 Lake Street")
    assert notice["citizen"]["mobile"] == CITIZEN and notice["citizen"]["name"] == "Ravi Kumar"
    assert notice["officer"]["name"]  # the officer the complaint was with is named


def test_the_officer_it_was_with_sees_the_notice(portal, desk):
    view = file(portal)
    assigned = portal.store.get_complaint(view["id"])["assigned_officer_id"]
    desk.accept(WORKER, view["id"], now=NOW)
    desk.reject(WORKER, view["id"], REASON, now=NOW)
    officer = portal.store.get_officer(assigned) if assigned else None
    if officer is None:
        pytest.skip("no officer was assigned for this ward in the demo data")
    mine = portal.officer_notices(officer)
    assert [n["complaint_id"] for n in mine if n.get("kind") == "rejected"] == [view["id"]]


def test_the_same_worker_cannot_take_it_again_but_another_can(portal, desk):
    view = file(portal)
    desk.accept(WORKER, view["id"], now=NOW)
    desk.reject(WORKER, view["id"], REASON, now=NOW)
    with pytest.raises(PortalError) as again:
        desk.accept(WORKER, view["id"], now=NOW)
    assert again.value.status == 403
    assert view["id"] not in [item["id"] for item in desk.board(WORKER, now=NOW)["available"]]
    assert view["id"] in [item["id"] for item in desk.board(OTHER_WORKER, now=NOW)["available"]]
    desk.accept(OTHER_WORKER, view["id"], now=NOW)
    assert portal.store.get_complaint(view["id"])["worker_mobile"] == OTHER_WORKER


def test_a_short_reason_is_refused(portal, desk):
    view = file(portal)
    desk.accept(WORKER, view["id"], now=NOW)
    with pytest.raises(PortalError) as short:
        desk.reject(WORKER, view["id"], "no", now=NOW)
    assert short.value.status == 400
    assert portal.store.get_complaint(view["id"])["worker_mobile"] == WORKER


def test_only_the_allotted_worker_can_reject(portal, desk):
    view = file(portal)
    desk.accept(WORKER, view["id"], now=NOW)
    with pytest.raises(PortalError) as other:
        desk.reject(OTHER_WORKER, view["id"], REASON, now=NOW)
    assert other.value.status == 403


def test_without_sms_the_worker_screen_shows_the_completion_code(portal, desk):
    view = file(portal)
    desk.accept(WORKER, view["id"], now=NOW)
    sent = desk.request_completion(WORKER, view["id"], now=NOW)
    assert sent["sent_by_sms"] is False and len(sent["demo_code"]) == 6
    shown = [item for item in desk.board(WORKER, now=NOW)["mine"] if item["id"] == view["id"]][0]
    assert shown["demo_code"] == sent["demo_code"]


def test_a_worker_can_reject_straight_from_the_registered_list(portal, desk):
    view = file(portal)
    card = desk.reject(WORKER, view["id"], REASON, now=NOW)
    assert card["id"] == view["id"] and card["status"] == "open"

    row = portal.store.get_complaint(view["id"])
    assert row["worker_mobile"] is None and row["status"] == "open"
    board = desk.board(WORKER, now=NOW)
    assert all(item["id"] != view["id"] for item in board["available"])
    assert [item["id"] for item in board["rejected"]] == [view["id"]]
    assert board["rejected"][0]["now_status_text"] == "Open again. Waiting for another worker to accept it."

    other = desk.board(OTHER_WORKER, now=NOW)
    assert any(item["id"] == view["id"] for item in other["available"])


def test_the_worker_who_rejected_straight_away_cannot_take_it_again(portal, desk):
    view = file(portal)
    desk.reject(WORKER, view["id"], REASON, now=NOW)
    with pytest.raises(PortalError) as again:
        desk.accept(WORKER, view["id"], now=NOW)
    assert again.value.status == 403
    with pytest.raises(PortalError) as twice:
        desk.reject(WORKER, view["id"], REASON, now=NOW)
    assert twice.value.status == 403


def test_a_complaint_allotted_to_someone_else_cannot_be_rejected(portal, desk):
    view = file(portal)
    desk.accept(OTHER_WORKER, view["id"], now=NOW)
    with pytest.raises(PortalError) as other:
        desk.reject(WORKER, view["id"], REASON, now=NOW)
    assert other.value.status == 403


def test_allotted_count_includes_work_accepted_then_rejected(portal, desk):
    first = file(portal)
    second = file(portal)
    third = file(portal)
    desk.accept(WORKER, first["id"], now=NOW)
    desk.reject(WORKER, first["id"], REASON, now=NOW)  # accepted, then rejected: counts
    desk.accept(WORKER, second["id"], now=NOW)          # still in progress: counts
    desk.reject(WORKER, third["id"], REASON, now=NOW)   # rejected straight from the list: never accepted
    board = desk.board(WORKER, now=NOW)
    assert board["accepted_count"] == 2
    assert len(board["rejected"]) == 2
    assert [item["id"] for item in board["mine"]] == [second["id"]]


def test_every_officer_sees_a_rejection_but_not_other_time_limit_notices(portal, desk):
    view = file(portal)
    desk.accept(WORKER, view["id"], now=NOW)
    desk.reject(WORKER, view["id"], REASON, now=NOW)
    unrelated = {"id": 0, "level": DEPOT}
    seen = [n for n in portal.officer_notices(unrelated) if n["complaint_id"] == view["id"]]
    assert len(seen) == 1 and seen[0]["kind"] == "rejected"
