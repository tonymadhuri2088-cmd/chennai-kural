"""Register Complaint: emergency or not emergency, the type from the list, three photos for a civic complaint."""

import base64
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "complaint_tools"))

# pylint: disable=wrong-import-position
from complaint_portal.categories import CIVIC_CATEGORIES, EMERGENCY_CATEGORIES  # noqa: E402
from complaint_portal.locations import load_locations  # noqa: E402
from complaint_portal.seed import seed_demo_officers  # noqa: E402
from complaint_portal.store import Store  # noqa: E402
from complaint_portal.workflow import PortalError, Portal  # noqa: E402

NOW = datetime(2026, 10, 18, 4, 0, tzinfo=timezone.utc)
CITIZEN = "9876543210"
HOME = "12 Main Road, Teynampet, Chennai"
TEXT = "Water is leaking from the pipe near the bus stop for three days."
ADDRESS = "No. 12, 4th Main Road, Teynampet, Chennai"


def jpeg(size=40):
    return "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * size).decode()


def make_portal(tmp_path):
    store = Store(tmp_path / "portal.db")
    seed_demo_officers(store, "a-long-password")
    portal = Portal(store)
    portal.sign_up_citizen("Ravi Kumar", CITIZEN, HOME, 115, now=NOW)
    return portal


def register(portal, **extra):
    options = dict(use_llm=False, now=NOW, address=ADDRESS, landmark="")
    options.update(extra)
    return portal.register("Ravi Kumar", CITIZEN, TEXT, ward_number=115, **options)


def test_the_lists_have_the_names_the_citizen_sees():
    assert len(EMERGENCY_CATEGORIES) == 13 and len(CIVIC_CATEGORIES) == 10
    assert EMERGENCY_CATEGORIES[0][1] == "Emergency Rescue"
    assert CIVIC_CATEGORIES[-1][1] == "Other Complaints"


def test_emergency_is_urgent_and_needs_no_photos(tmp_path):
    portal = make_portal(tmp_path)
    view = register(portal, kind="emergency", category="fire_smoke")
    assert portal.store.get_complaint(view["id"])["urgent"] == 1
    assert view["complaint_kind"] == "emergency"
    assert view["category_label"] == "Fire and smoke emergencies"
    assert view["photo_count"] == 0


def test_civic_needs_exactly_three_photos(tmp_path):
    portal = make_portal(tmp_path)
    with pytest.raises(PortalError) as short:
        register(portal, kind="civic", category="water_supply", photos=[jpeg(), jpeg()])
    assert "3 photos" in short.value.message
    with pytest.raises(PortalError):
        register(portal, kind="civic", category="water_supply", photos=[jpeg()] * 4)


def test_civic_photos_are_saved_and_counted(tmp_path):
    portal = make_portal(tmp_path)
    view = register(portal, kind="civic", category="drainage_sewerage", photos=[jpeg(), jpeg(), jpeg()])
    assert view["complaint_kind"] == "civic"
    assert view["category_label"] == "Drainage and Sewerage"
    assert view["photo_count"] == 3
    saved = sorted(p.name for p in (tmp_path / "photos").iterdir())
    assert saved == [f"{view['id']}-{n}.jpg" for n in (1, 2, 3)]


def test_wrong_category_for_the_kind_is_refused(tmp_path):
    portal = make_portal(tmp_path)
    with pytest.raises(PortalError) as wrong:
        register(portal, kind="civic", category="fire_smoke", photos=[jpeg()] * 3)
    assert "from the list" in wrong.value.message
    with pytest.raises(PortalError) as unknown:
        register(portal, kind="other", category="water_supply")
    assert "Emergency or Not emergency" in unknown.value.message


def test_a_file_that_is_not_a_picture_is_refused(tmp_path):
    portal = make_portal(tmp_path)
    fake = "data:image/png;base64," + base64.b64encode(b"this is text, not a picture").decode()
    with pytest.raises(PortalError) as raised:
        register(portal, kind="civic", category="water_supply", photos=[jpeg(), jpeg(), fake])
    assert "not a real picture" in raised.value.message


def test_old_apps_without_the_new_fields_still_file_the_complaint(tmp_path):
    portal = make_portal(tmp_path)
    view = register(portal)
    assert view["id"] and view["photo_count"] == 0 and view["complaint_kind"] is None


def test_register_page_offers_both_kinds_and_the_three_photos():
    page = (ROOT / "portal" / "register.html").read_text(encoding="utf-8")
    assert 'value="emergency"' in page and 'value="civic"' in page
    assert "Upload 3 photos" in page or "Add photo" in page
    assert "Add address" in page and "todayLine" in page
    for _, label in EMERGENCY_CATEGORIES + CIVIC_CATEGORIES:
        assert label.replace("&", "&amp;") in page or label in page
