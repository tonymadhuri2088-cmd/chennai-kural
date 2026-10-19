"""Field workers: sign-up, login with a code, accepting complaints, and completing them with the citizen's code.

A worker signs up once with the same details as a citizen plus the department they work in, then logs in
with a code to their mobile number. They see every open complaint that no worker has taken yet and can
accept one; the citizen then sees "Allotted" and "Work in progress". To mark it completed, the worker asks
for a code that goes to the citizen's mobile number (this demo shows it on the citizen's screen instead of
sending an SMS). Only the right code completes the complaint, which closes it as resolved.
"""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from complaint_portal.auth import CODE_MINUTES
from complaint_portal.locations import parse_ward_number
from complaint_portal.rules import CLOSED, OPEN
from complaint_portal.workflow import (
    ALREADY_SIGNED_UP,
    MAX_ADDRESS_CHARS,
    MIN_ADDRESS_CHARS,
    NEW_USER,
    Portal,
    PortalError,
    clean_text,
    iso,
    mask_number,
    normalise_contact,
    utcnow,
)

MAX_DEPARTMENT_CHARS = 60
MIN_REASON_CHARS = 10
MAX_REASON_CHARS = 500
NOT_YOURS = "This complaint is not one of your allotted tasks."
REJECTED_BEFORE = "You rejected this complaint earlier, so you cannot take it again."


def _login_key(mobile: str) -> str:
    return f"worker-login:{mobile}"


def _complete_key(complaint_id: str) -> str:
    return f"complete:{complaint_id}"


def mask_mobile(mobile: str) -> str:
    """98XXXXXX10: enough for the worker to know where the code went, without showing the whole number."""
    return mask_number(mobile)


class WorkerDesk:
    """Everything a worker does. It shares the portal's store, codes and complaint views."""

    def __init__(self, portal: Portal) -> None:
        self.portal = portal
        self.store = portal.store

    # Sign-up and login

    def sign_up(self, name: Any, contact: Any, address: Any, ward_number: Any, department: Any,
                now: Optional[datetime] = None) -> Dict[str, Any]:
        now = now or utcnow()
        name = name.strip() if isinstance(name, str) else ""
        address = clean_text(address, MAX_ADDRESS_CHARS)
        department = department.strip() if isinstance(department, str) else ""
        digits = normalise_contact(contact)
        if not 2 <= len(name) <= 100:
            raise PortalError(400, "Enter your name (2 to 100 characters).")
        if len(digits) != 10:
            raise PortalError(400, "Enter a 10-digit mobile number.")
        if len(address) < MIN_ADDRESS_CHARS:
            raise PortalError(400, "Give your address in detail, with your street and area (at least 10 characters).")
        if not 2 <= len(department) <= MAX_DEPARTMENT_CHARS:
            raise PortalError(400, f"Enter the department you work in (2 to {MAX_DEPARTMENT_CHARS} characters).")
        ward = self.portal.locations.ward(parse_ward_number(ward_number) or 0)
        if ward is None:
            raise PortalError(400, "Choose your ward from the list (wards 1 to 200).")
        zone = self.portal.locations.zone(ward.zone_number)
        if not self.store.create_worker(digits, name, address, zone.number, zone.name, ward.number, ward.name,
                                        department, iso(now)):
            raise PortalError(409, ALREADY_SIGNED_UP)
        return {"message": "Sign-up saved. Log in with your mobile number on the Worker Login tab."}

    def start_login(self, contact: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
        now = now or utcnow()
        digits = normalise_contact(contact)
        if len(digits) != 10:
            raise PortalError(400, "Enter a 10-digit mobile number.")
        if self.store.get_worker(digits) is None:
            raise PortalError(404, NEW_USER)
        code = self.portal.codes.issue(_login_key(digits), now, digits)
        return {"minutes": CODE_MINUTES, **self.portal.deliver_code(digits, code, "login")}

    def verify_login(self, contact: Any, code: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
        now = now or utcnow()
        digits = normalise_contact(contact)
        if len(digits) != 10:
            raise PortalError(400, "Enter a 10-digit mobile number.")
        outcome, payload = self.portal.codes.check(_login_key(digits), code, now)
        _raise_for(outcome, "Ask for a code first: enter your mobile number and press Send me a code.")
        return self.profile(payload)

    def profile(self, mobile: str) -> Dict[str, Any]:
        row = self.store.get_worker(mobile)
        if row is None:
            raise PortalError(401, "Log in as a worker first.")
        ward = self.portal.locations.ward(row["ward_number"])
        zone = self.portal.locations.zone(row["zone_number"])
        return {
            "mobile": row["mobile"],
            "name": row["name"],
            "address": row["address"],
            "department": row["department"],
            "zone": f"{zone.name} zone",
            "ward": ward.label(),
            "ward_number": ward.number,
            "zone_number": zone.number,
        }

    # The worker's board

    def board(self, mobile: str, now: Optional[datetime] = None) -> Dict[str, Any]:
        """Open complaints nobody has taken yet (the worker's own zone first), and the worker's allotted tasks."""
        now = now or utcnow()
        me = self.profile(mobile)
        available = self.store.list_complaints("status = ? AND worker_mobile IS NULL", (OPEN,), limit=300)
        available = [row for row in available if not self._rejected_by(row["id"], mobile)]
        available.sort(key=lambda row: 0 if row.get("zone_number") == me["zone_number"] else 1)
        mine = self.store.list_complaints("worker_mobile = ?", (mobile,), limit=300)
        completed = self.store.list_complaints("completed_by = ?", (mobile,), limit=300)
        rejected = self._rejections(mobile)
        # Every complaint this worker has accepted: still in progress, completed, or rejected after accepting.
        # Complaints rejected straight from the registered list were never accepted, so they are not counted.
        accepted_count = len(mine) + sum(1 for item in rejected if item.get("accepted_at"))
        return {
            "available": [self._card(row, now) for row in available],
            "mine": [self._card(row, now) for row in mine],
            "completed": [self._card(row, now) for row in completed],
            "rejected": rejected,
            "accepted_count": accepted_count,
        }

    def _rejections(self, mobile: str) -> List[Dict[str, Any]]:
        """Complaints this worker rejected, with the reason and what has happened since."""
        items = []
        for notice in self.store.list_notices(None, limit=500):
            payload = json.loads(notice["payload"])
            worker = payload.get("worker") or {}
            if payload.get("kind") != "rejected" or worker.get("mobile") != mobile:
                continue
            row = self.store.get_complaint(notice["complaint_id"])
            if row is None:
                continue
            if row["status"] == CLOSED:
                now_text = "Resolved by another worker."
            elif row.get("worker_mobile"):
                now_text = "Accepted by another worker."
            else:
                now_text = "Open again. Waiting for another worker to accept it."
            items.append({
                "id": row["id"],
                "complaint_label": payload.get("complaint_label"),
                "complaint_text": payload.get("complaint_text"),
                "problem_address": payload.get("problem_address"),
                "landmark": payload.get("landmark"),
                "reason": payload.get("reason"),
                "rejected_at": worker.get("rejected_at"),
                "accepted_at": worker.get("accepted_at"),
                "office": payload.get("office"),
                "now_status_text": now_text,
            })
        items.sort(key=lambda item: item["rejected_at"] or "", reverse=True)
        return items

    def _card(self, row: Dict[str, Any], now: datetime) -> Dict[str, Any]:
        view = self.portal._summary(row, now)  # pylint: disable=protected-access
        view.update({
            "complaint_text": row["complaint_text"],
            "landmark": row.get("landmark"),
            "registered_at": row["created_at"],
            "accepted_at": row.get("worker_accepted_at"),
            "completed_at": row.get("completed_at"),
            "citizen": self.portal.citizen_brief(row["citizen_contact"]),
            "code_sent": row["status"] == OPEN and self.portal.codes.pending(_complete_key(row["id"]), now),
            "demo_code": self._demo_code(row, now),
        })
        return view

    def _demo_code(self, row: Dict[str, Any], now: datetime) -> Optional[str]:
        """Only when no SMS is set up: the completion code is shown on the worker's screen, so it can be checked."""
        shown = self.portal.completion_codes.get(row["id"])
        if shown is None or row["status"] != OPEN or now >= shown[1]:
            return None
        return shown[0]

    def _rejected_by(self, complaint_id: str, mobile: str) -> bool:
        """True if this worker rejected the complaint before, so it is not offered to them again."""
        return any(event["kind"] == "rejected" and event["actor"] == f"worker:{mobile}"
                   for event in self.store.get_events(complaint_id))

    # Accept and complete

    def accept(self, mobile: str, complaint_id: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
        now = now or utcnow()
        me = self.profile(mobile)
        row = self._row(complaint_id)
        if row["status"] != OPEN:
            raise PortalError(409, "This complaint is already resolved or closed.")
        if self._rejected_by(row["id"], mobile):
            raise PortalError(403, REJECTED_BEFORE)
        if not self.store.claim_complaint(row["id"], mobile, iso(now)):
            raise PortalError(409, "Another worker has already accepted this complaint.")
        self.store.add_event(row["id"], iso(now), f"worker:{mobile}", "allotted",
                             f"Allotted to {me['name']} ({me['department']}). Work in progress.")
        return self._card(self.store.get_complaint(row["id"]), now)

    def request_completion(self, mobile: str, complaint_id: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
        """Send a code to the citizen's mobile number. The worker enters it to mark the complaint completed."""
        now = now or utcnow()
        row = self._mine(mobile, complaint_id)
        code = self.portal.codes.issue(_complete_key(row["id"]), now, mobile)
        delivery = self.portal.deliver_code(row["citizen_contact"], code, "complete")
        demo_code = None
        if delivery.get("sent_by_sms"):
            self.portal.completion_codes.pop(row["id"], None)
            note = "The code was sent to the citizen by SMS."
        else:
            # No SMS: the citizen's Track Complaint and Home pages show the code, and so does the worker's screen.
            self.portal.completion_codes[row["id"]] = (code, now + timedelta(minutes=CODE_MINUTES))
            demo_code = code
            note = "No SMS was sent, so the code appears on the citizen's Track Complaint and Home pages."
        self.store.add_event(row["id"], iso(now), f"worker:{mobile}", "completion_code",
                             "The worker asked to mark the work completed. A code was sent to the citizen's mobile number.")
        return {
            "sent_to": mask_mobile(row["citizen_contact"]),
            "minutes": CODE_MINUTES,
            "sent_by_sms": bool(delivery.get("sent_by_sms")),
            "demo_code": demo_code,
            "note": note,
        }

    def complete(self, mobile: str, complaint_id: Any, code: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
        """Close the complaint as resolved, only if the code the citizen received matches."""
        now = now or utcnow()
        me = self.profile(mobile)
        row = self._mine(mobile, complaint_id)
        outcome, payload = self.portal.codes.check(_complete_key(row["id"]), code, now)
        _raise_for(outcome, "Ask for a code first: press Mark as completed.")
        if payload != mobile:
            raise PortalError(400, "That code does not match.")
        self.portal.completion_codes.pop(row["id"], None)
        self.store.update_complaint(
            row["id"],
            status=CLOSED,
            stage_deadline=None,
            completed_at=iso(now),
            completed_by=mobile,
            resolution_note=f"Completed by {me['name']} ({me['department']}).",
            updated_at=iso(now),
        )
        self.store.add_event(row["id"], iso(now), f"worker:{mobile}", "completed",
                             f"Completed by {me['name']} ({me['department']}). The citizen's code matched. Resolved.")
        return self._card(self.store.get_complaint(row["id"]), now)

    def reject(self, mobile: str, complaint_id: Any, reason: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
        """The worker gives the complaint back, with a reason. The officer gets a notice with the details.

        A worker can reject a complaint straight from the list of complaints nobody has taken yet, or from
        their own allotted tasks. Either way the complaint stays open and goes back to the list, so another
        worker can accept it. This worker cannot take it again.
        """
        now = now or utcnow()
        me = self.profile(mobile)
        row = self._open_for_reject(mobile, complaint_id)
        text = reason.strip() if isinstance(reason, str) else ""
        if not MIN_REASON_CHARS <= len(text) <= MAX_REASON_CHARS:
            raise PortalError(400, f"Write why you are rejecting it ({MIN_REASON_CHARS} to {MAX_REASON_CHARS} characters).")
        worker = self.store.get_worker(mobile)
        self.portal.completion_codes.pop(row["id"], None)
        self.store.release_complaint(row["id"], iso(now))
        self.store.add_event(row["id"], iso(now), f"worker:{mobile}", "rejected",
                             f"Rejected by {me['name']} ({me['department']}, {mobile}). Reason: {text}. "
                             "The complaint is open again for another worker, and the officer has been told.")
        self.portal.record_rejection(row, worker, text, now)
        return self._card(self.store.get_complaint(row["id"]), now)

    # Helpers

    def _open_for_reject(self, mobile: str, complaint_id: Any) -> Dict[str, Any]:
        """A complaint this worker may reject: open, and either theirs already or not taken by anyone yet."""
        row = self._row(complaint_id)
        if row["status"] != OPEN:
            raise PortalError(409, "This complaint is already resolved or closed.")
        holder = row.get("worker_mobile")
        if holder not in (None, "", mobile):
            raise PortalError(403, NOT_YOURS)
        if not holder and self._rejected_by(row["id"], mobile):
            raise PortalError(403, REJECTED_BEFORE)
        return row

    def _row(self, complaint_id: Any) -> Dict[str, Any]:
        row = self.store.get_complaint(str(complaint_id or "").strip().upper())
        if row is None:
            raise PortalError(404, "We could not find that complaint.")
        return row

    def _mine(self, mobile: str, complaint_id: Any) -> Dict[str, Any]:
        row = self._row(complaint_id)
        if row.get("worker_mobile") != mobile:
            raise PortalError(403, NOT_YOURS)
        if row["status"] != OPEN:
            raise PortalError(409, "This complaint is already resolved or closed.")
        return row


def _raise_for(outcome: str, none_message: str) -> None:
    if outcome == "ok":
        return
    if outcome == "none":
        raise PortalError(400, none_message)
    if outcome == "expired":
        raise PortalError(400, "That code has expired. Ask for a new one.")
    if outcome == "locked":
        raise PortalError(400, "Too many wrong codes. Ask for a new one.")
    raise PortalError(400, "That code does not match.")
