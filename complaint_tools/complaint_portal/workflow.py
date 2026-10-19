"""The complaint workflow.

A citizen signs up once with their name, mobile number, address and ward. After that they log in
with a code sent to their registered mobile number, and the login stays until they log out. Their
address narrows the choice to a zone, and the citizen picks their ward from that zone. A complaint
is registered under the citizen's ward, sorted into a field, and sent to the owning depot. The depot
marks it resolved. The citizen then says whether it is fixed. If it is, a confirmation code is shown
to them and the complaint closes when they enter it. If it is not fixed, the complaint goes to the
ward office and then to the District Head Office. A time limit at any level also moves the complaint up.

Officers sign up and log in with their username and password. Officer logins end at midnight every day (India time).
"""

import base64
import binascii
import json
import re
from pathlib import Path
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from complaintrouter.common import load_charter
from complaintrouter.pipeline import run_complaint
from complaint_portal.auth import CODE_MINUTES, OneTimeCodes, hash_password, verify_password
from complaint_portal.sms import NoSms
from complaint_portal.categories import (
    CIVIC, EMERGENCY, KINDS, MAX_PHOTO_BYTES, PHOTO_TYPES, PHOTOS_REQUIRED, categories_for, category_label,
)
from complaint_portal.locations import LocationData, load_locations, match_zones, parse_ward_number
from complaint_portal.rules import (
    AWAITING,
    CLOSED,
    DEPOT,
    DISTRICT_HEAD,
    FIELD_ALL,
    FIELDS,
    OPEN,
    STAGES,
    STATUS_TEXT,
    field_for,
    level_name,
    officer_level_for,
    path_after_citizen_not_fixed,
    stage_label,
    stage_path,
    stage_window,
)
from complaint_portal import router_link
from complaint_portal.store import Store

MAX_NOTE_CHARS = 1000
MIN_ADDRESS_CHARS = 10
MAX_ADDRESS_CHARS = 300
MAX_LANDMARK_CHARS = 100
NOT_FOUND_CITIZEN = "No complaint matches this ID and mobile number."
NOT_VISIBLE = "No complaint with that ID is visible to you."
NEW_USER = "You are new user, please sign up."
ALREADY_SIGNED_UP = "This mobile number already has an account. Log in with it instead."
USERNAME_RULE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,39}$")
EMAIL_RULE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PortalError(Exception):
    """An error the web server turns into an HTTP status and a plain message."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


KIND_NAMES = {EMERGENCY: "Emergency", CIVIC: "Not emergency"}


def _is_image(raw: bytes, mime: str) -> bool:
    if mime == "image/jpeg":
        return raw[:3] == b"\xff\xd8\xff"
    if mime == "image/png":
        return raw[:8] == b"\x89PNG\r\n\x1a\n"
    return raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(moment: datetime) -> str:
    """Store times as UTC, to the second, so they sort correctly as text."""
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def normalise_contact(raw: Any) -> str:
    """Keep the digits of a mobile number. A leading 91 country code is removed."""
    digits = re.sub(r"\D", "", raw) if isinstance(raw, str) else ""
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits


def _place(row: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """The zone and ward a complaint was filed under, as text for the screens. Older rows may have none."""
    if not row.get("ward_number"):
        return {"zone": None, "ward": None}
    name = row.get("ward_name")
    ward = f"Ward {row['ward_number']}" + (f", {name}" if name else "")
    return {"zone": f"{row['zone_name']} zone", "ward": ward}


def mask_number(mobile: str) -> str:
    """98XXXXXX10: enough to know where a code went, without showing the whole number."""
    return mobile[:2] + "X" * max(0, len(mobile) - 4) + mobile[-2:] if len(mobile) >= 4 else mobile


def _work_status(row: Dict[str, Any]) -> Optional[str]:
    """'allotted' while a worker has it, 'completed' once the worker finished it with the citizen's code."""
    if row.get("completed_at"):
        return "completed"
    if row.get("worker_mobile") and row["status"] == OPEN:
        return "allotted"
    return None


def _login_key(mobile: str) -> str:
    return f"login:{mobile}"


def _confirm_key(complaint_id: str) -> str:
    return f"confirm:{complaint_id}"


def clean_text(value: Any, limit: int, required: bool = False) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if required and not text:
        raise PortalError(400, "Write a short note first.")
    if len(text) > limit:
        raise PortalError(400, f"The note is longer than {limit} characters.")
    return text


class Portal:
    """All complaint actions. The web server and the tests both call this class."""

    def __init__(self, store: Store, locations: Optional[LocationData] = None,
                 demo_minutes: Optional[float] = None, sms: Any = None) -> None:
        self.store = store
        # Sends the codes by SMS when a provider is set up (see sms.py). Otherwise codes are shown on screen.
        self.sms = sms or NoSms()
        self.locations = locations or load_locations()
        # One-time codes for citizen logins ("login:<mobile>"), for confirming a fix ("confirm:<complaint ID>"),
        # for worker logins ("worker-login:<mobile>") and for a worker's completion ("complete:<complaint ID>").
        self.codes = OneTimeCodes()
        # Demo only: every time limit becomes this many minutes, so passing a time limit can be shown live.
        self.demo_minutes = demo_minutes if demo_minutes and demo_minutes > 0 else None
        # Completion codes, kept so the citizen's screen can show them (a stand-in for an SMS): ID -> (code, expires).
        self.completion_codes: Dict[str, Tuple[str, datetime]] = {}

    def deliver_code(self, mobile: str, code: str, purpose: str) -> Dict[str, Any]:
        """Send a code by SMS when a provider is set up. Returns what the screen should say.

        Sent: {"sent_by_sms": True, "sent_to": "98XXXXXX10", "note": ...} and no code.
        Not sent (no provider, or the provider failed): {"code": code, "note": ...}, so the code is shown on screen.
        """
        if self.sms.configured:
            sent, detail = self.sms.send_code(mobile, code, CODE_MINUTES, purpose)
            if sent:
                return {
                    "sent_by_sms": True,
                    "sent_to": mask_number(mobile),
                    "note": f"We sent a 6-digit code by SMS to {mask_number(mobile)}.",
                }
            print(f"SMS to {mask_number(mobile)} failed: {detail}")
            return {"code": code, "sent_by_sms": False,
                    "note": f"The SMS could not be sent ({detail}) The code is shown here instead."}
        return {"code": code, "sent_by_sms": False,
                "note": "This demo shows the code here instead of sending it by SMS."}

    def _window(self, fix_days: Optional[int], fix_hours: Optional[int], escalation_key: Optional[str],
                stage: str, charter: Dict[str, Any]) -> Optional[timedelta]:
        """The time limit at a stage: from the charter timeline, or the demo minutes when they are set."""
        if self.demo_minutes:
            return timedelta(minutes=self.demo_minutes)
        return stage_window(fix_days, fix_hours, escalation_key, stage, charter)

    # Citizen login

    def match_address(self, address: Any) -> Dict[str, Any]:
        """Use the address to narrow the choice to zones. The citizen still picks the ward."""
        text = clean_text(address, MAX_ADDRESS_CHARS)
        if len(text) < MIN_ADDRESS_CHARS:
            raise PortalError(400, "Give your address in detail, with your street and area (at least 10 characters).")
        tree = self.locations.tree()["zones"]
        matches = match_zones(text, self.locations)
        if matches:
            order = {number: index for index, (number, _) in enumerate(matches)}
            zones = sorted((zone for zone in tree if zone["number"] in order), key=lambda zone: order[zone["number"]])
            names = ", ".join(f"{zone['name']} zone" for zone in zones)
            note = f"Your address matches {names}. Choose your ward from these zones."
        else:
            zones = tree
            note = "No zone name in your address matched the data. Choose your ward from all zones."
        return {"matched": bool(matches), "note": note, "zones": zones}

    def sign_up_citizen(self, name: Any, contact: Any, address: Any, ward_number: Any,
                        now: Optional[datetime] = None) -> Dict[str, Any]:
        """Store a new citizen's details. The citizen then logs in with their mobile number."""
        now = now or utcnow()
        name = name.strip() if isinstance(name, str) else ""
        address = clean_text(address, MAX_ADDRESS_CHARS)
        digits = normalise_contact(contact)
        if not 2 <= len(name) <= 100:
            raise PortalError(400, "Enter your name (2 to 100 characters).")
        if len(digits) != 10:
            raise PortalError(400, "Enter a 10-digit mobile number.")
        if len(address) < MIN_ADDRESS_CHARS:
            raise PortalError(400, "Give your address in detail, with your street and area (at least 10 characters).")
        ward = self.locations.ward(parse_ward_number(ward_number) or 0)
        if ward is None:
            raise PortalError(400, "Choose your ward from the list (wards 1 to 200).")
        zone = self.locations.zone(ward.zone_number)
        created = self.store.create_citizen(digits, name, address, zone.number, zone.name,
                                            ward.number, ward.name, iso(now))
        if not created:
            raise PortalError(409, ALREADY_SIGNED_UP)
        return {"message": "Sign-up saved. Log in with your mobile number."}

    def start_citizen_login(self, contact: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
        """Issue a code for a registered mobile number. The code is shown on screen (demo); no SMS is sent."""
        now = now or utcnow()
        digits = normalise_contact(contact)
        if len(digits) != 10:
            raise PortalError(400, "Enter a 10-digit mobile number.")
        if self.store.get_citizen(digits) is None:
            raise PortalError(404, NEW_USER)
        code = self.codes.issue(_login_key(digits), now, digits)
        return {"minutes": CODE_MINUTES, **self.deliver_code(digits, code, "login")}

    def verify_login(self, contact: Any, code: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
        """Check the code and return the citizen's profile. The caller starts the login session."""
        now = now or utcnow()
        digits = normalise_contact(contact)
        if len(digits) != 10:
            raise PortalError(400, "Enter a 10-digit mobile number.")
        outcome, payload = self.codes.check(_login_key(digits), code, now)
        if outcome == "none":
            raise PortalError(400, "Ask for a code first: enter your mobile number and press Send me a code.")
        if outcome == "expired":
            raise PortalError(400, "That code has expired. Ask for a new one.")
        if outcome == "locked":
            raise PortalError(400, "Too many wrong codes. Ask for a new one.")
        if outcome == "wrong":
            raise PortalError(400, "That code does not match.")
        return self.citizen_profile(payload)

    def citizen_profile(self, mobile: str) -> Dict[str, Any]:
        row = self.store.get_citizen(mobile)
        if row is None:
            raise PortalError(401, "Log in first.")
        ward = self.locations.ward(row["ward_number"])
        zone = self.locations.zone(row["zone_number"])
        return {
            "mobile": row["mobile"],
            "name": row["name"],
            "address": row["address"],
            "zone": f"{zone.name} zone",
            "ward": ward.label(),
            "ward_number": ward.number,
        }

    def citizen_complaints(self, mobile: str, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Every complaint filed with this mobile number, newest first."""
        now = now or utcnow()
        rows = self.store.list_complaints("citizen_contact = ?", (mobile,))
        return [self._summary(row, now) for row in rows]

    # Citizen actions

    def _check_kind(self, kind: Any, category: Any, photos: Any) -> Tuple[Optional[str], Optional[str], List[str]]:
        """Check the emergency or civic choice, the category, and the photos. Old apps send none of these."""
        if kind is None and category is None and photos is None:
            return None, None, []
        if kind not in KINDS:
            raise PortalError(400, "Choose Emergency or Not emergency.")
        keys = [key for key, _ in categories_for(kind)]
        if category not in keys:
            raise PortalError(400, "Choose the type of complaint from the list.")
        images = photos if isinstance(photos, list) else []
        if kind == CIVIC and len(images) != PHOTOS_REQUIRED:
            raise PortalError(400, f"Upload {PHOTOS_REQUIRED} photos of the problem.")
        if kind == EMERGENCY:
            images = []  # emergencies are not held up for photos
        return kind, category, images

    def _save_photos(self, cid: str, images: List[str]) -> List[str]:
        """Write the photos in a photos folder next to the database. Returns the file names."""
        if not images:
            return []
        folder = Path(self.store.path).parent / "photos"
        folder.mkdir(parents=True, exist_ok=True)
        names = []
        for number, image in enumerate(images, start=1):
            if not isinstance(image, str) or not image.startswith("data:") or ";base64," not in image:
                raise PortalError(400, "A photo could not be read. Choose the photo again.")
            head, data = image.split(";base64,", 1)
            mime = head[5:].lower()
            if mime not in PHOTO_TYPES:
                raise PortalError(400, "Photos must be JPEG, PNG or WebP pictures.")
            try:
                raw = base64.b64decode(data, validate=True)
            except (binascii.Error, ValueError):
                raise PortalError(400, "A photo could not be read. Choose the photo again.") from None
            if not raw or len(raw) > MAX_PHOTO_BYTES:
                raise PortalError(400, "Each photo must be smaller than 4 MB.")
            if not _is_image(raw, mime):
                raise PortalError(400, "A file is not a real picture. Choose the photo again.")
            extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[mime]
            name = f"{cid}-{number}.{extension}"
            (folder / name).write_bytes(raw)
            names.append(name)
        return names

    def register(self, name: Any, contact: Any, complaint: Any, ward_number: Any = None,
                 use_llm: bool = True, now: Optional[datetime] = None,
                 address: Any = None, landmark: Any = None, kind: Any = None, category: Any = None,
                 photos: Any = None) -> Dict[str, Any]:
        """File a complaint. address is where the problem is (None: not given); landmark is optional.

        kind is "emergency" or "civic" (the citizen's choice); category is one key from categories.py.
        photos is a list of up to PHOTOS_REQUIRED images as data: URLs. Civic complaints need all of them.
        Older apps send none of these, and then the complaint is filed as before.
        """
        now = now or utcnow()
        name = name.strip() if isinstance(name, str) else ""
        complaint = complaint.strip() if isinstance(complaint, str) else ""
        digits = normalise_contact(contact)
        if not 2 <= len(name) <= 100:
            raise PortalError(400, "Enter your name (2 to 100 characters).")
        if len(digits) != 10:
            raise PortalError(400, "Enter a 10-digit mobile number.")
        if not 10 <= len(complaint) <= 2000:
            raise PortalError(400, "Describe the complaint in 10 to 2000 characters.")
        problem_address = None
        if address is not None:
            problem_address = address.strip() if isinstance(address, str) else ""
            if not MIN_ADDRESS_CHARS <= len(problem_address) <= MAX_ADDRESS_CHARS:
                raise PortalError(400, "Give the address of the problem, with the street and area "
                                       f"({MIN_ADDRESS_CHARS} to {MAX_ADDRESS_CHARS} characters).")
        landmark_text = landmark.strip() if isinstance(landmark, str) else ""
        if len(landmark_text) > MAX_LANDMARK_CHARS:
            raise PortalError(400, f"Keep the landmark under {MAX_LANDMARK_CHARS} characters.")
        ward = self.locations.ward(parse_ward_number(ward_number) or 0)
        if ward is None:
            raise PortalError(400, "Choose your ward from the list (wards 1 to 200).")
        zone = self.locations.zone(ward.zone_number)
        kind, category_key, images = self._check_kind(kind, category, photos)

        # The ID is chosen first so the router's message can name the real complaint, not "to be assigned".
        cid = self.store.new_complaint_id(now)
        result = run_complaint(complaint, None, use_llm=use_llm, reference=cid)
        classification = result["classification"]
        timeline = result["timeline"]
        routing = result["route"]
        charter = load_charter()

        complaint_type = classification["complaint_type"]
        field = field_for(complaint_type)
        escalation_key = routing.get("escalation_key")
        owner_label = routing.get("owner") or "the field office"
        window = self._window(timeline.get("fix_days"), timeline.get("fix_hours"), escalation_key, DEPOT, charter)
        officer = self.store.find_officer(field, DEPOT, ward.zone_number)
        photo_files = self._save_photos(cid, images)
        urgent = bool(classification["urgent"]) or kind == EMERGENCY

        self.store.insert_complaint({
            "id": cid,
            "created_at": iso(now),
            "updated_at": iso(now),
            "citizen_name": name,
            "citizen_contact": digits,
            "complaint_text": complaint,
            "complaint_type": complaint_type,
            "subtype": classification["subtype"],
            "urgent": 1 if urgent else 0,
            "classifier": classification["classifier"],
            "field": field,
            "escalation_key": escalation_key,
            "owner_label": owner_label,
            "fix_days": timeline.get("fix_days"),
            "fix_hours": timeline.get("fix_hours"),
            "stage_path": json.dumps(stage_path(escalation_key)),
            "stage": DEPOT,
            "stage_since": iso(now),
            "stage_deadline": iso(now + window) if window else None,
            "status": OPEN,
            "assigned_officer_id": officer["id"] if officer else None,
            "resolution_note": None,
            "zone_number": zone.number,
            "zone_name": zone.name,
            "ward_number": ward.number,
            "ward_name": ward.name,
            "problem_address": problem_address,
            "landmark": landmark_text or None,
            "complaint_kind": kind,
            "category": category_key,
            "photo_files": json.dumps(photo_files) if photo_files else None,
            # What the router produced: its message to the citizen (exact text) and its timeline.
            "router_message": result["reply"],
            "router_timeline": json.dumps(router_link.snapshot(result, charter)),
        })
        self.store.add_event(cid, iso(now), "system", "registered",
                             f"Registered under {FIELDS[field]}. Ward {ward.number}, {zone.name} zone. Sent to {owner_label}.")
        if kind:
            self.store.add_event(cid, iso(now), "system", "category",
                                 f"{KIND_NAMES[kind]}: {category_label(kind, category_key)}.")
        if urgent and kind == EMERGENCY:
            self.store.add_event(cid, iso(now), "system", "urgent", "Emergency complaint. Please act first.")
        elif classification["urgent"]:
            self.store.add_event(cid, iso(now), "system", "urgent", "Marked urgent from the wording of the complaint. Please act first.")
        if officer:
            self.store.add_event(cid, iso(now), "system", "assigned", f"Assigned to {officer['name']}.")
        else:
            self.store.add_event(cid, iso(now), "system", "unassigned", "No officer is set up for this field at this level yet. Waiting for assignment.")
        return self._public(self.store.get_complaint(cid))

    def track(self, complaint_id: Any, contact: Any) -> Dict[str, Any]:
        return self._public(self._citizen_row(complaint_id, contact))

    def confirm(self, complaint_id: Any, contact: Any, fixed: Any, comment: Any = "", now: Optional[datetime] = None) -> Dict[str, Any]:
        """The citizen says the problem is fixed (closes it) or not fixed (escalates it)."""
        now = now or utcnow()
        row = self._citizen_row(complaint_id, contact)
        if row["status"] != AWAITING:
            raise PortalError(409, "This complaint is not waiting for your confirmation.")
        if not isinstance(fixed, bool):
            raise PortalError(400, "Say whether the problem is fixed.")
        comment = clean_text(comment, MAX_NOTE_CHARS)
        suffix = f" Comment: {comment}" if comment else ""

        if fixed:
            # Nothing closes yet. The citizen must enter the code shown to them here.
            code = self.codes.issue(_confirm_key(row["id"]), now)
            delivery = self.deliver_code(row["citizen_contact"], code, "confirm")
            how = "sent to them by SMS" if delivery.get("sent_by_sms") else "shown to them"
            self.store.add_event(row["id"], iso(now), "citizen", "code_issued",
                                 f"The citizen says the problem is fixed. A confirmation code was {how}." + suffix)
            view = self._public(self.store.get_complaint(row["id"]), now)
            if "code" in delivery:
                view["demo_code"] = code
                view["demo_code_minutes"] = CODE_MINUTES
            view["code_note"] = delivery["note"]
            return view

        self.codes.drop(_confirm_key(row["id"]))
        self.store.update_complaint(row["id"], status=OPEN, updated_at=iso(now))
        self.store.add_event(row["id"], iso(now), "citizen", "not_fixed", "The citizen says the problem is not fixed." + suffix)
        current = self.store.get_complaint(row["id"])
        if current["stage"] == DISTRICT_HEAD:
            self.store.add_event(row["id"], iso(now), "system", "final_level", "This complaint is already with the District Head Office.")
        else:
            new_path = path_after_citizen_not_fixed(json.loads(current["stage_path"]), current["stage"])
            self.store.update_complaint(row["id"], stage_path=json.dumps(new_path))
            self._escalate(self.store.get_complaint(row["id"]), now, "The citizen says the problem is not fixed", "citizen")
        return self._public(self.store.get_complaint(row["id"]), now)

    def confirm_code(self, complaint_id: Any, contact: Any, code: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
        """The citizen enters the code. A matching code closes the complaint as fixed."""
        now = now or utcnow()
        row = self._citizen_row(complaint_id, contact)
        if row["status"] != AWAITING:
            raise PortalError(409, "This complaint is not waiting for your confirmation.")
        outcome, _ = self.codes.check(_confirm_key(row["id"]), code, now)
        if outcome == "none":
            raise PortalError(409, "Say the problem is fixed first, to get a confirmation code.")
        if outcome == "expired":
            raise PortalError(400, "That code has expired. Say the problem is fixed again to get a new one.")
        if outcome == "locked":
            raise PortalError(400, "Too many wrong codes. Say the problem is fixed again to get a new one.")
        if outcome == "wrong":
            raise PortalError(400, "That code does not match.")
        self.store.update_complaint(row["id"], status=CLOSED, updated_at=iso(now))
        self.store.add_event(row["id"], iso(now), "citizen", "closed", "The citizen entered the code. The complaint is closed as fixed.")
        return self._public(self.store.get_complaint(row["id"]), now)

    # Officer actions

    def sign_up_officer(self, fields: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
        """Store an officer sign-up as pending. The District Head Office must approve it before it can log in."""
        now = now or utcnow()

        def text(key: str, low: int, high: int, message: str) -> str:
            value = fields.get(key)
            value = value.strip() if isinstance(value, str) else ""
            if not low <= len(value) <= high:
                raise PortalError(400, message)
            return value

        name = text("name", 2, 100, "Enter your name (2 to 100 characters).")
        employee_id = text("employee_id", 2, 30, "Enter your employee ID (2 to 30 characters).")
        position = text("position", 2, 100, "Enter your position or designation.")
        email = text("email", 5, 120, "Enter your email address.")
        if not EMAIL_RULE.match(email):
            raise PortalError(400, "Enter a valid email address.")
        digits = normalise_contact(fields.get("mobile"))
        if len(digits) != 10:
            raise PortalError(400, "Enter a 10-digit mobile number.")
        username = text("username", 3, 40, "Choose a username (3 to 40 characters).")
        if not USERNAME_RULE.match(username):
            raise PortalError(400, "A username uses lower-case letters, numbers, dots, dashes and underscores only.")
        password = fields.get("password") if isinstance(fields.get("password"), str) else ""
        if len(password) < 10:
            raise PortalError(400, "Use a password of at least 10 characters.")
        field = fields.get("field")
        if field not in FIELDS:
            raise PortalError(400, "Choose the field you work in.")
        level = fields.get("level")
        if level not in STAGES or level == DISTRICT_HEAD:
            raise PortalError(400, "Choose your level. The District Head Office account is set up by an administrator.")
        zone_number = None
        zone_raw = fields.get("zone_number")
        if zone_raw not in (None, "", "all"):
            number = int(zone_raw) if str(zone_raw).isdigit() else None
            if number is None or self.locations.zone(number) is None:
                raise PortalError(400, "Choose a zone from 1 to 15, or all zones.")
            zone_number = number
        if self.store.get_officer_by_username(username):
            raise PortalError(409, "That username is already taken. Choose another.")
        try:
            self.store.insert_officer(username, name, field, level, hash_password(password), zone_number,
                                      employee_id=employee_id, position=position, mobile=digits, email=email,
                                      status="pending", at=iso(now))
        except sqlite3.IntegrityError:
            raise PortalError(409, "That username is already taken. Choose another.") from None
        return {"message": "Sign-up saved. Log in with your username and password."}

    def login(self, username: Any, password: Any) -> Dict[str, Any]:
        row = self.store.get_officer_by_username(username.strip() if isinstance(username, str) else "")
        if row is None:
            raise PortalError(404, NEW_USER)
        if not verify_password(password if isinstance(password, str) else "", row["password_hash"]):
            raise PortalError(401, "Wrong username or password.")
        # Officer accounts can log in with the right username and password, even before the District Head Office
        # approves them. (Approval is still recorded; to require it again, check row["status"] here.)
        return self.officer_view(row)

    def officer_list(self, officer: Dict[str, Any], now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        now = now or utcnow()
        if officer["level"] == DISTRICT_HEAD:
            rows = self.store.list_complaints()
        else:
            rows = self.store.list_complaints("assigned_officer_id = ?", (officer["id"],))
        return [self._summary(row, now) for row in rows]

    def officer_detail(self, officer: Dict[str, Any], complaint_id: str, now: Optional[datetime] = None) -> Dict[str, Any]:
        now = now or utcnow()
        return self._detail_for(self._visible(officer, complaint_id), officer, now)

    def _detail_for(self, row: Dict[str, Any], officer: Dict[str, Any], now: datetime) -> Dict[str, Any]:
        """Build the officer's view of a complaint row. Used after an action that may move the complaint away from this officer."""
        charter = load_charter()
        path = json.loads(row["stage_path"])
        assigned = row["assigned_officer_id"] == officer["id"]
        is_head = officer["level"] == DISTRICT_HEAD
        has_next = path.index(row["stage"]) + 1 < len(path)
        return {
            **self._summary(row, now),
            "complaint_text": row["complaint_text"],
            "citizen_name": row["citizen_name"],
            "citizen_contact": row["citizen_contact"],
            "urgent": bool(row["urgent"]),
            "classifier": row["classifier"],
            "path": [stage_label(stage, charter, row["owner_label"]) for stage in path],
            "current_stage": row["stage"],
            "resolution_note": row["resolution_note"],
            "events": [
                {"at": event["at"], "actor": event["actor"], "kind": event["kind"], "message": event["message"]}
                for event in self.store.get_events(row["id"])
            ],
            "can_resolve": assigned and row["status"] == OPEN,
            "can_escalate": (assigned or is_head) and row["status"] == OPEN and has_next,
            "can_note": (assigned or is_head) and row["status"] != CLOSED,
        }

    def resolve(self, officer: Dict[str, Any], complaint_id: str, note: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
        """The assigned officer marks the complaint resolved. The citizen must then confirm."""
        now = now or utcnow()
        row = self._visible(officer, complaint_id)
        if row["assigned_officer_id"] != officer["id"]:
            raise PortalError(403, "Only the officer this complaint is assigned to can mark it resolved.")
        if row["status"] != OPEN:
            raise PortalError(409, "Only an open complaint can be marked resolved.")
        note = clean_text(note, MAX_NOTE_CHARS, required=True)
        self.store.update_complaint(row["id"], status=AWAITING, stage_deadline=None, resolution_note=note, updated_at=iso(now))
        self.store.add_event(row["id"], iso(now), officer["username"], "resolved", f"Marked resolved: {note.rstrip('.')}. Waiting for the citizen to confirm.")
        return self.officer_detail(officer, row["id"], now)

    def add_note(self, officer: Dict[str, Any], complaint_id: str, note: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
        now = now or utcnow()
        row = self._visible(officer, complaint_id)
        if row["status"] == CLOSED:
            raise PortalError(409, "This complaint is closed.")
        note = clean_text(note, MAX_NOTE_CHARS, required=True)
        self.store.add_event(row["id"], iso(now), officer["username"], "note", note)
        self.store.update_complaint(row["id"], updated_at=iso(now))
        return self.officer_detail(officer, row["id"], now)

    def escalate(self, officer: Dict[str, Any], complaint_id: str, note: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
        now = now or utcnow()
        row = self._visible(officer, complaint_id)
        if row["status"] != OPEN:
            raise PortalError(409, "Only an open complaint can be escalated.")
        note = clean_text(note, MAX_NOTE_CHARS, required=True)
        if not self._escalate(row, now, f"Escalated by {officer['name']}: {note}", officer["username"]):
            raise PortalError(409, "This complaint is already with the District Head Office.")
        # The complaint has moved to the next officer, so show it as this officer no longer sees it.
        return self._detail_for(self.store.get_complaint(row["id"]), officer, now)

    def check_overdue(self, now: Optional[datetime] = None) -> List[str]:
        """Move every open complaint whose time limit has passed. Return the IDs moved."""
        now = now or utcnow()
        charter = load_charter()
        rows = self.store.list_complaints(
            "status = ? AND stage_deadline IS NOT NULL AND stage_deadline <= ?",
            (OPEN, iso(now)),
            limit=1000,
        )
        moved = []
        for row in rows:
            current = stage_label(row["stage"], charter, row["owner_label"])
            if self._escalate(row, now, f"The time limit at {current} has passed", "system"):
                moved.append(row["id"])
                after = self.store.get_complaint(row["id"])
                self._record_notice(row, now, stage_label(after["stage"], charter, after["owner_label"]),
                                    after["assigned_officer_id"])
            else:
                # Already at the last level: it stays there, but the officers still get one notice.
                self._record_notice(row, now, None, None)
        return moved

    # Shared helpers

    def officer_view(self, row: Dict[str, Any]) -> Dict[str, Any]:
        charter = load_charter()
        return {
            "id": row["id"],
            "username": row["username"],
            "name": row["name"],
            "field": row["field"],
            "field_label": "All fields" if row["field"] == FIELD_ALL else FIELDS[row["field"]],
            "level": row["level"],
            "level_label": level_name(row["level"], charter),
            "is_district_head": row["level"] == DISTRICT_HEAD,
        }

    def _escalate(self, row: Dict[str, Any], now: datetime, reason: str, actor: str) -> bool:
        """Move a complaint to the next level and assign that level's officer. False if already at the last level."""
        path = json.loads(row["stage_path"])
        index = path.index(row["stage"])
        if index + 1 >= len(path):
            return False
        next_stage = path[index + 1]
        charter = load_charter()
        window = self._window(row["fix_days"], row["fix_hours"], row["escalation_key"], next_stage, charter)
        officer = self.store.find_officer(row["field"], officer_level_for(next_stage), row["zone_number"])
        self.store.update_complaint(
            row["id"],
            stage=next_stage,
            stage_since=iso(now),
            stage_deadline=iso(now + window) if window else None,
            status=OPEN,
            assigned_officer_id=officer["id"] if officer else None,
            updated_at=iso(now),
        )
        label = stage_label(next_stage, charter, row["owner_label"])
        self.store.add_event(row["id"], iso(now), actor, "escalated", f"{reason}. Moved to {label}.")
        if officer:
            self.store.add_event(row["id"], iso(now), "system", "assigned", f"Assigned to {officer['name']}.")
        else:
            self.store.add_event(row["id"], iso(now), "system", "unassigned", "No officer is set up at this level yet. Waiting for assignment.")
        return True

    def _citizen_row(self, complaint_id: Any, contact: Any) -> Dict[str, Any]:
        """The citizen sees a complaint only with both its ID and the mobile number it was filed with."""
        row = self.store.get_complaint(str(complaint_id or "").strip().upper())
        if row is None or row["citizen_contact"] != normalise_contact(contact):
            raise PortalError(404, NOT_FOUND_CITIZEN)
        return row

    def _visible(self, officer: Dict[str, Any], complaint_id: Any) -> Dict[str, Any]:
        """Officers see complaints assigned to them. The District Head Office sees all."""
        row = self.store.get_complaint(str(complaint_id or "").strip().upper())
        if row is None:
            raise PortalError(404, NOT_VISIBLE)
        if officer["level"] != DISTRICT_HEAD and row["assigned_officer_id"] != officer["id"]:
            raise PortalError(404, NOT_VISIBLE)
        return row

    def _public(self, row: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
        now = now or utcnow()
        charter = load_charter()
        officer = self.store.get_officer(row["assigned_officer_id"]) if row["assigned_officer_id"] else None
        type_label = charter["complaint_types"].get(row["complaint_type"], {}).get("label", "General grievance")
        return {
            "id": row["id"],
            "field": FIELDS[row["field"]],
            "complaint_label": type_label,
            "complaint_text": row["complaint_text"],
            "status": row["status"],
            "status_text": self._status_text(row),
            "current_office": stage_label(row["stage"], charter, row["owner_label"]),
            "assigned_to": officer["name"] if officer else "Waiting for an officer to be assigned",
            **_place(row),
            "problem_address": row.get("problem_address"),
            "landmark": row.get("landmark"),
            "complaint_kind": row.get("complaint_kind"),
            "category": row.get("category"),
            "category_label": category_label(row.get("complaint_kind") or "", row.get("category") or ""),
            "photo_count": len(json.loads(row["photo_files"])) if row.get("photo_files") else 0,
            "deadline": row["stage_deadline"],
            "created_at": row["created_at"],
            "work_status": _work_status(row),
            "rejected_before": self._rejected_before(row),
            "worker": self._worker_brief(row),
            "completed_at": row.get("completed_at"),
            **self._shown_completion_code(row, now),
            "can_confirm": row["status"] == AWAITING,
            "awaiting_code": row["status"] == AWAITING and self.codes.pending(_confirm_key(row["id"]), now),
            "events": [{"at": event["at"], "message": event["message"]} for event in self.store.get_events(row["id"])],
            # From the router. The message is None for a complaint filed before it was kept.
            "router_message": row.get("router_message"),
            "router_progress": router_link.progress(row, charter),
        }

    def _status_text(self, row: Dict[str, Any]) -> str:
        """The status in words, including a worker's part."""
        if row["status"] == CLOSED and row.get("completed_at"):
            return "Resolved. The worker completed it and the citizen's code was checked."
        if row["status"] == OPEN and row.get("worker_mobile"):
            worker = self.store.get_worker(row["worker_mobile"])
            who = f"{worker['name']} ({worker['department']})" if worker else "a worker"
            return f"Allotted to {who}. Work in progress."
        if row["status"] == OPEN and self._rejected_before(row):
            return "Rejected by a worker earlier. Back in progress, waiting for another worker to accept it."
        return STATUS_TEXT[row["status"]]

    def _rejected_before(self, row: Dict[str, Any]) -> bool:
        """True if a worker rejected this complaint at some point (it may be back in progress now)."""
        return any(event["kind"] == "rejected" for event in self.store.get_events(row["id"]))

    def _worker_brief(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """The worker who accepted the complaint, or None."""
        if not row.get("worker_mobile"):
            return None
        worker = self.store.get_worker(row["worker_mobile"])
        if worker is None:
            return None
        return {
            "name": worker["name"],
            "mobile": worker["mobile"],
            "department": worker["department"],
            "accepted_at": row.get("worker_accepted_at"),
        }

    def _shown_completion_code(self, row: Dict[str, Any], now: datetime) -> Dict[str, Any]:
        """The code a worker asked for, shown to the citizen (this demo shows it instead of sending an SMS)."""
        shown = self.completion_codes.get(row["id"])
        if shown is None or row["status"] != OPEN or now >= shown[1]:
            return {"completion_code": None}
        return {"completion_code": shown[0], "completion_code_minutes": CODE_MINUTES}

    def citizen_brief(self, mobile: str) -> Dict[str, Any]:
        """What the citizen gave at sign-up, for the worker and the officer."""
        row = self.store.get_citizen(mobile)
        if row is None:
            return {"name": None, "mobile": mobile, "address": None, "zone": None, "ward": None}
        ward = self.locations.ward(row["ward_number"])
        zone = self.locations.zone(row["zone_number"])
        return {
            "name": row["name"],
            "mobile": row["mobile"],
            "address": row["address"],
            "zone": f"{zone.name} zone" if zone else row.get("zone_name"),
            "ward": ward.label() if ward else f"Ward {row['ward_number']}",
        }

    def officer_notices(self, officer: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Notices for this officer: complaints that passed their time limit, plus every complaint a worker rejected.

        Every officer sees every rejection, so nothing given back by a worker is missed. Time-limit notices only go to
        the officer they were sent to. The District Head Office sees every notice.
        """
        if officer["level"] == DISTRICT_HEAD:
            rows = self.store.list_notices(None)
        else:
            rows = self.store.list_notices(officer["id"])
            seen = {row["id"] for row in rows}
            for row in self.store.list_notices(None, limit=500):
                if row["id"] not in seen and json.loads(row["payload"]).get("kind") == "rejected":
                    rows.append(row)
            rows.sort(key=lambda row: row["id"], reverse=True)
        notices = []
        for row in rows:
            payload = json.loads(row["payload"])
            current = self.store.get_complaint(row["complaint_id"])
            payload.update({
                "notice_id": row["id"],
                "created_at": row["created_at"],
                "now_status": current["status"] if current else None,
                "now_status_text": self._status_text(current) if current else None,
            })
            notices.append(payload)
        return notices

    def _record_notice(self, row: Dict[str, Any], now: datetime, moved_to: Optional[str],
                       to_officer_id: Optional[int]) -> None:
        """Keep a notice for the officers: the complaint, the citizen and any worker, when a time limit passes."""
        charter = load_charter()
        type_label = charter["complaint_types"].get(row["complaint_type"], {}).get("label", "General grievance")
        worker = self._worker_brief(row)
        payload = {
            "complaint_id": row["id"],
            "complaint_label": type_label,
            "complaint_text": row["complaint_text"],
            "department": FIELDS[row["field"]],
            "office": stage_label(row["stage"], charter, row["owner_label"]),
            "moved_to": moved_to,
            "deadline": row["stage_deadline"],
            "registered_at": row["created_at"],
            "problem_address": row.get("problem_address"),
            "landmark": row.get("landmark"),
            "complaint_kind": row.get("complaint_kind"),
            "category": row.get("category"),
            "category_label": category_label(row.get("complaint_kind") or "", row.get("category") or ""),
            "photo_count": len(json.loads(row["photo_files"])) if row.get("photo_files") else 0,
            **_place(row),
            "citizen": self.citizen_brief(row["citizen_contact"]),
            "worker": worker,
        }
        self.store.add_notice(row["id"], row["stage"], iso(now), row["assigned_officer_id"], to_officer_id,
                              json.dumps(payload))

    def record_rejection(self, row: Dict[str, Any], worker: Dict[str, Any], reason: str, now: datetime) -> None:
        """Tell the officer that a worker rejected the complaint, with the worker, the citizen and the officer's details.

        The notice goes to the officer the complaint is with (the District Head Office sees every notice).
        The worker is passed in as it was before the rejection, because the complaint no longer has one.
        """
        charter = load_charter()
        type_label = charter["complaint_types"].get(row["complaint_type"], {}).get("label", "General grievance")
        officer = self.store.get_officer(row["assigned_officer_id"]) if row.get("assigned_officer_id") else None
        payload = {
            "kind": "rejected",
            "complaint_id": row["id"],
            "complaint_label": type_label,
            "complaint_text": row["complaint_text"],
            "department": FIELDS[row["field"]],
            "office": stage_label(row["stage"], charter, row["owner_label"]),
            "moved_to": None,
            "deadline": None,
            "registered_at": row["created_at"],
            "problem_address": row.get("problem_address"),
            "landmark": row.get("landmark"),
            "complaint_kind": row.get("complaint_kind"),
            "category": row.get("category"),
            "category_label": category_label(row.get("complaint_kind") or "", row.get("category") or ""),
            "photo_count": len(json.loads(row["photo_files"])) if row.get("photo_files") else 0,
            **_place(row),
            "citizen": self.citizen_brief(row["citizen_contact"]),
            "worker": {
                "name": worker["name"],
                "mobile": worker["mobile"],
                "department": worker["department"],
                "position": worker["department"],
                "address": worker.get("address"),
                "zone": worker.get("zone_name"),
                "ward": worker.get("ward_name"),
                "accepted_at": row.get("worker_accepted_at"),
                "rejected_at": iso(now),
            },
            "reason": reason,
            "officer": {
                "name": officer["name"] if officer else None,
                "position": officer.get("position") if officer else None,
                "mobile": officer.get("mobile") if officer else None,
                "email": officer.get("email") if officer else None,
                "employee_id": officer.get("employee_id") if officer else None,
                "level": officer.get("level") if officer else None,
                "office": stage_label(row["stage"], charter, row["owner_label"]),
            },
        }
        to_officer = row.get("assigned_officer_id")
        self.store.add_notice(row["id"], f"rejected-{iso(now)}", iso(now), None, to_officer, json.dumps(payload))

    def _summary(self, row: Dict[str, Any], now: datetime) -> Dict[str, Any]:
        charter = load_charter()
        officer = self.store.get_officer(row["assigned_officer_id"]) if row["assigned_officer_id"] else None
        type_label = charter["complaint_types"].get(row["complaint_type"], {}).get("label", "General grievance")
        overdue = row["status"] == OPEN and bool(row["stage_deadline"]) and row["stage_deadline"] < iso(now)
        return {
            "id": row["id"],
            "complaint_label": type_label,
            "field": FIELDS[row["field"]],
            "current_office": stage_label(row["stage"], charter, row["owner_label"]),
            "status": row["status"],
            "status_text": self._status_text(row),
            "deadline": row["stage_deadline"],
            "overdue": overdue,
            "work_status": _work_status(row),
            "rejected_before": self._rejected_before(row),
            "worker": self._worker_brief(row),
            "assigned_to": officer["name"] if officer else "Not assigned",
            **_place(row),
            "problem_address": row.get("problem_address"),
            "landmark": row.get("landmark"),
            "complaint_kind": row.get("complaint_kind"),
            "category": row.get("category"),
            "category_label": category_label(row.get("complaint_kind") or "", row.get("category") or ""),
            "photo_count": len(json.loads(row["photo_files"])) if row.get("photo_files") else 0,
            "updated_at": row["updated_at"],
        }
