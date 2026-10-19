"""Tests for the Chennai ward dataset and how the portal uses it.

No LLM or internet is needed. The ward data is read from the data/ folder. Tests that need
broken data write their own small files in a temporary folder.
"""

import csv
import importlib.util
import json
import shutil
import sqlite3
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "complaint_tools"))

# pylint: disable=wrong-import-position
from complaint_portal.auth import Sessions, hash_password  # noqa: E402
from complaint_portal.locations import (  # noqa: E402
    TOTAL_WARDS,
    cmwssb_sewer_zones,
    load_locations,
    parse_ward_number,
)
from complaint_portal.rules import DEPOT, DISTRICT_HEAD, FIELDS  # noqa: E402
from complaint_portal.store import COMPLAINT_COLUMNS, Store  # noqa: E402
from complaint_portal.workflow import PortalError, Portal  # noqa: E402

_spec = importlib.util.spec_from_file_location("portal_server", ROOT / "portal" / "server.py")
portal_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(portal_server)

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
CONTACT = "98765 43210"
LEAK = "Water is leaking from the pipe near my house for three days, please fix it."
HASH = hash_password("portal-test-pass")


@pytest.fixture(scope="module")
def locations():
    return load_locations()


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "portal.db")


def copy_data(tmp_path: Path) -> Path:
    """Copy the three data files into a temporary folder so a test can break one of them."""
    folder = tmp_path / "data"
    folder.mkdir()
    for name in ("chennai_zones.csv", "chennai_wards.csv", "cmwssb_sewer_zones.csv"):
        shutil.copy(ROOT / "data" / name, folder / name)
    return folder


def rewrite_csv(path: Path, rows, fields):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


# The dataset itself

def test_dataset_has_15_zones_and_200_wards(locations):
    assert len(locations.zones) == 15
    assert len(locations.wards) == TOTAL_WARDS == 200
    assert sorted(locations.wards) == list(range(1, 201))


def test_zone_ranges_run_without_gaps(locations):
    expected = 1
    for number in sorted(locations.zones):
        zone = locations.zones[number]
        assert zone.ward_from == expected
        assert zone.ward_to - zone.ward_from + 1 >= 8
        expected = zone.ward_to + 1
    assert expected == 201


def test_every_ward_sits_inside_its_zone(locations):
    for ward in locations.wards.values():
        zone = locations.zone(ward.zone_number)
        assert zone.ward_from <= ward.number <= zone.ward_to


@pytest.mark.parametrize("ward, zone_name", [
    (1, "Thiruvottiyur"),
    (14, "Thiruvottiyur"),
    (15, "Manali"),
    (115, "Teynampet"),
    (143, "Valasaravakkam"),
    (200, "Sholinganallur"),
])
def test_known_wards_map_to_the_gazette_zone(locations, ward, zone_name):
    assert locations.ward(ward).zone_name == zone_name


def test_ward_names_are_blank_because_no_source_gives_them(locations):
    assert all(ward.name is None for ward in locations.wards.values())
    assert locations.ward(115).label() == "Ward 115"


def test_tree_lists_every_ward_under_its_zone(locations):
    tree = locations.tree()
    assert tree["district"] == "Chennai"
    assert tree["ward_count"] == 200
    assert len(tree["zones"]) == 15
    assert sum(len(zone["wards"]) for zone in tree["zones"]) == 200
    teynampet = next(zone for zone in tree["zones"] if zone["name"] == "Teynampet")
    assert [ward["number"] for ward in teynampet["wards"]] == list(range(109, 127))


def test_cmwssb_sewer_zones_are_listed_for_reference():
    zones = cmwssb_sewer_zones()
    assert [zone["sewer_zone"] for zone in zones] == ["Zone-1", "Zone-2", "Zone-3", "Zone-4", "Zone-5"]
    assert all("verify" in zone["source"].lower() for zone in zones)


# Loader checks

def test_loader_rejects_a_missing_ward(tmp_path):
    folder = copy_data(tmp_path)
    rows = list(csv.DictReader(open(folder / "chennai_wards.csv", encoding="utf-8")))
    rows = [row for row in rows if row["ward_number"] != "50"]
    rewrite_csv(folder / "chennai_wards.csv", rows, rows[0].keys())
    with pytest.raises(ValueError, match="once each"):
        load_locations(folder)


def test_loader_rejects_a_ward_under_the_wrong_zone(tmp_path):
    folder = copy_data(tmp_path)
    rows = list(csv.DictReader(open(folder / "chennai_wards.csv", encoding="utf-8")))
    for row in rows:
        if row["ward_number"] == "1":
            row["zone_number"] = "2"
    rewrite_csv(folder / "chennai_wards.csv", rows, rows[0].keys())
    with pytest.raises(ValueError, match="does not contain it"):
        load_locations(folder)


def test_loader_rejects_zone_ranges_with_a_gap(tmp_path):
    folder = copy_data(tmp_path)
    rows = list(csv.DictReader(open(folder / "chennai_zones.csv", encoding="utf-8")))
    rows[1]["ward_from"] = "16"
    rows[1]["ward_count"] = str(int(rows[1]["ward_to"]) - 16 + 1)
    rewrite_csv(folder / "chennai_zones.csv", rows, rows[0].keys())
    with pytest.raises(ValueError):
        load_locations(folder)


def test_loader_rejects_a_count_that_does_not_match_its_range(tmp_path):
    folder = copy_data(tmp_path)
    rows = list(csv.DictReader(open(folder / "chennai_zones.csv", encoding="utf-8")))
    rows[0]["ward_count"] = "99"
    rewrite_csv(folder / "chennai_zones.csv", rows, rows[0].keys())
    with pytest.raises(ValueError, match="ward_count"):
        load_locations(folder)


def test_ward_names_are_used_when_a_source_gives_them(tmp_path):
    folder = copy_data(tmp_path)
    rows = list(csv.DictReader(open(folder / "chennai_wards.csv", encoding="utf-8")))
    for row in rows:
        if row["ward_number"] == "115":
            row["ward_name"] = "Example Nagar"
    rewrite_csv(folder / "chennai_wards.csv", rows, rows[0].keys())
    data = load_locations(folder)
    assert data.ward(115).label() == "Ward 115, Example Nagar"


# Parsing a ward number

@pytest.mark.parametrize("raw, expected", [
    (115, 115), ("115", 115), (" 7 ", 7), (1, 1), (200, 200),
    (0, None), (201, None), ("abc", None), ("", None), (None, None),
    (True, None), (7.0, None), ("7.5", None), ("-3", None),
])
def test_parse_ward_number(raw, expected):
    assert parse_ward_number(raw) == expected


# Using the wards in the portal

@pytest.fixture
def staffed(store):
    for field in FIELDS:
        store.insert_officer(f"{field}.depot", f"{FIELDS[field]} depot", field, DEPOT, HASH)
    store.insert_officer("district.head", "District Head Office", "all", DISTRICT_HEAD, HASH)
    return store


def test_register_records_zone_and_ward(staffed):
    portal = Portal(staffed)
    view = portal.register("Ravi", CONTACT, LEAK, ward_number="115", use_llm=False, now=NOW)
    assert view["zone"] == "Teynampet zone"
    assert view["ward"] == "Ward 115"
    row = staffed.get_complaint(view["id"])
    assert row["zone_number"] == 9
    assert row["ward_number"] == 115
    messages = [event["message"] for event in staffed.get_events(view["id"])]
    assert any("Ward 115, Teynampet zone" in message for message in messages)


@pytest.mark.parametrize("ward", [None, "", 0, 201, "many", True])
def test_register_refuses_a_missing_or_bad_ward(staffed, ward):
    with pytest.raises(PortalError) as raised:
        Portal(staffed).register("Ravi", CONTACT, LEAK, ward_number=ward, use_llm=False, now=NOW)
    assert raised.value.status == 400
    assert "wards 1 to 200" in raised.value.message


def test_zone_officer_is_preferred_over_the_city_wide_one(staffed):
    staffed.insert_officer("water.depot.zone9", "Water depot, Teynampet zone", "water", DEPOT, HASH, zone_number=9)
    view = Portal(staffed).register("Ravi", CONTACT, LEAK, ward_number=115, use_llm=False, now=NOW)
    assert view["assigned_to"] == "Water depot, Teynampet zone"

    other = Portal(staffed).register("Asha", CONTACT, LEAK, ward_number=1, use_llm=False, now=NOW)
    assert other["assigned_to"] == "Water supply depot"


def test_escalation_keeps_the_zone_when_choosing_the_next_officer(staffed):
    staffed.insert_officer("water.deputy.zone9", "Water deputy, Teynampet zone", "water", "deputy_ae", HASH, zone_number=9)
    staffed.insert_officer("water.deputy", "Water deputy, city", "water", "deputy_ae", HASH)
    portal = Portal(staffed)
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=115, use_llm=False, now=NOW)
    moved = portal.check_overdue(NOW + timedelta(days=10))
    assert view["id"] in moved
    assert staffed.get_officer(staffed.get_complaint(view["id"])["assigned_officer_id"])["username"] == "water.deputy.zone9"


def test_district_head_still_sees_every_complaint(staffed):
    portal = Portal(staffed)
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=115, use_llm=False, now=NOW)
    head = staffed.get_officer_by_username("district.head")
    assert view["id"] in [row["id"] for row in portal.officer_list(head)]


def test_officer_detail_shows_the_place(staffed):
    portal = Portal(staffed)
    view = portal.register("Ravi", CONTACT, LEAK, ward_number=115, use_llm=False, now=NOW)
    depot = staffed.get_officer_by_username("water.depot")
    detail = portal.officer_detail(depot, view["id"], now=NOW)
    assert detail["zone"] == "Teynampet zone"
    assert detail["ward"] == "Ward 115"


def test_old_database_files_gain_the_new_columns(tmp_path):
    path = tmp_path / "old.db"
    old_complaint_columns = [name for name in COMPLAINT_COLUMNS if name not in
                             ("zone_number", "zone_name", "ward_number", "ward_name", "problem_address", "landmark")]
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE complaints (" + ", ".join(f"{name} TEXT" for name in old_complaint_columns) + ")")
        conn.execute("CREATE TABLE officers (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, name TEXT, "
                     "field TEXT, level TEXT, password_hash TEXT)")
    Store(path)
    with sqlite3.connect(path) as conn:
        complaint_cols = {row[1] for row in conn.execute("PRAGMA table_info(complaints)")}
        officer_cols = {row[1] for row in conn.execute("PRAGMA table_info(officers)")}
    assert {"zone_number", "zone_name", "ward_number", "ward_name", "problem_address", "landmark"} <= complaint_cols
    assert "zone_number" in officer_cols


# Web API for wards

@pytest.fixture
def server_url(staffed):
    httpd = portal_server.make_server("127.0.0.1", 0, Portal(staffed), Sessions())
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    yield f"http://{host}:{port}"
    httpd.shutdown()
    httpd.server_close()


def post(base, path, payload):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(base + path, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_locations_endpoint_is_public_and_complete(server_url):
    with urllib.request.urlopen(server_url + "/api/locations", timeout=10) as response:
        data = json.loads(response.read())
    assert data["ward_count"] == 200
    assert len(data["zones"]) == 15


def test_sign_up_must_include_a_ward_over_http(server_url):
    status, body = post(server_url, "/api/citizen/signup", {
        "name": "Ravi Kumar", "contact": CONTACT, "address": "14 Pillaiyar Koil Street, Teynampet, Chennai"})
    assert status == 400
    assert "wards 1 to 200" in body["error"]


def test_filing_needs_a_citizen_login_over_http(server_url):
    status, body = post(server_url, "/api/complaints", {"complaint": LEAK, "use_llm": False})
    assert status == 401
    assert "Log in" in body["error"]


def test_citizen_signs_up_logs_in_and_files_under_the_chosen_ward_over_http(server_url):
    status, body = post(server_url, "/api/citizen/signup", {
        "name": "Ravi Kumar", "contact": CONTACT, "address": "14 Pillaiyar Koil Street, Teynampet, Chennai",
        "ward_number": "115"})
    assert status == 201
    status, started = post(server_url, "/api/citizen/login", {"contact": CONTACT})
    assert status == 200
    status, _, headers = post_with_headers(server_url, "/api/citizen/verify",
                                           {"contact": CONTACT, "code": started["code"]})
    assert status == 200
    cookie = headers.get("Set-Cookie").split(";")[0]
    status, body, _ = post_with_headers(server_url, "/api/complaints", {"complaint": LEAK, "use_llm": False},
                                        cookie=cookie)
    assert status == 201
    assert body["zone"] == "Teynampet zone"
    assert body["ward"] == "Ward 115"


def post_with_headers(base, path, payload, cookie=None):
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    request = urllib.request.Request(base + path, data=json.dumps(payload).encode("utf-8"),
                                     headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read()), response.headers
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read()), error.headers
