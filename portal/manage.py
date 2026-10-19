"""Set-up commands for the complaint portal: the database and officer accounts.

Run from the project root:

    python portal/manage.py seed-demo --password "a-long-password"
    python portal/manage.py add-officer --username water.depot2 --name "Water: Depot Engineer (Zone 2)" --field water --level depot
    python portal/manage.py list-officers
    python portal/manage.py list-pending
    python portal/manage.py approve-officer --username water.depot2
    python portal/manage.py check-overdue

Fields: water, sewerage, billing, new_connection, general, or all (District Head Office only).
Levels: depot, deputy_ae, area_engineer, superintendent_engineer, district_head.
"""

import argparse
import getpass
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "complaint_tools"))

# pylint: disable=wrong-import-position
from complaint_portal.auth import hash_password  # noqa: E402
from complaint_portal.locations import load_locations  # noqa: E402
from complaint_portal.rules import DISTRICT_HEAD, FIELD_ALL, FIELDS, STAGES  # noqa: E402
from complaint_portal.seed import seed_demo_officers  # noqa: E402
from complaint_portal.store import Store  # noqa: E402
from complaint_portal.workflow import Portal, utcnow  # noqa: E402

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "portal.db"


def open_store(args) -> Store:
    return Store(args.db or os.environ.get("COMPLAINT_PORTAL_DB", str(DEFAULT_DB)))


def cmd_seed_demo(args) -> None:
    store = open_store(args)
    password = args.password or getpass.getpass("Password for the demo accounts (at least 8 characters): ")
    created = seed_demo_officers(store, password)
    print(f"Created {len(created)} account(s).")
    for username in created:
        print(f"  {username}")
    print("Change these passwords before any real use. Existing accounts were left as they were.")


def cmd_add_officer(args) -> None:
    if args.field not in list(FIELDS) + [FIELD_ALL]:
        raise SystemExit(f"Unknown field '{args.field}'. Use one of: {', '.join(list(FIELDS) + [FIELD_ALL])}.")
    if args.level not in STAGES:
        raise SystemExit(f"Unknown level '{args.level}'. Use one of: {', '.join(STAGES)}.")
    if (args.level == DISTRICT_HEAD) != (args.field == FIELD_ALL):
        raise SystemExit("The district_head level must use field 'all', and field 'all' must use the district_head level.")
    password = getpass.getpass("Password for the new officer (at least 8 characters): ")
    if len(password) < 8:
        raise SystemExit("Use a password of at least 8 characters.")
    zone_number = None
    if args.zone is not None:
        if load_locations().zone(args.zone) is None:
            raise SystemExit("Unknown zone. Zones are numbered 1 to 15 (see data/chennai_zones.csv).")
        zone_number = args.zone
    store = open_store(args)
    if store.get_officer_by_username(args.username):
        raise SystemExit(f"The username '{args.username}' already exists.")
    store.insert_officer(args.username, args.name, args.field, args.level, hash_password(password), zone_number)
    scope = f" for zone {zone_number}" if zone_number else " (all zones)"
    print(f"Added {args.username} ({args.name}){scope}.")


def cmd_list_officers(args) -> None:
    store = open_store(args)
    officers = store.list_officers()
    if not officers:
        print("No officers yet. Run seed-demo or add-officer.")
        return
    for officer in officers:
        print(f"{officer['username']:<32} {officer['field']:<15} {officer['level']:<26} {officer['status']:<10} {officer['name']}")


def cmd_list_pending(args) -> None:
    pending = [officer for officer in open_store(args).list_officers() if officer["status"] == "pending"]
    if not pending:
        print("No officer sign-ups are waiting for approval.")
        return
    for officer in pending:
        print(f"{officer['username']:<32} {officer['field']:<15} {officer['level']:<26} {officer['employee_id'] or '':<12} {officer['name']}")


def cmd_approve_officer(args) -> None:
    if not open_store(args).set_officer_status(args.username, "approved"):
        raise SystemExit(f"No officer has the username '{args.username}'.")
    print(f"Approved {args.username}. They can log in now.")


def cmd_check_overdue(args) -> None:
    portal = Portal(open_store(args))
    moved = portal.check_overdue(utcnow())
    print(f"Escalated {len(moved)} complaint(s) past their time limit.")
    for cid in moved:
        print(f"  {cid}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Set up and maintain the complaint portal.")
    parser.add_argument("--db", default=None, help="Database file (default portal/data/portal.db).")
    commands = parser.add_subparsers(dest="command", required=True)

    seed = commands.add_parser("seed-demo", help="Create demo accounts for every field and level.")
    seed.add_argument("--password", default=None, help="Password for the demo accounts. Prompted if left out.")
    seed.set_defaults(func=cmd_seed_demo)

    add = commands.add_parser("add-officer", help="Add one officer account.")
    add.add_argument("--username", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--field", required=True)
    add.add_argument("--level", required=True)
    add.add_argument("--zone", type=int, default=None,
                     help="Zone number 1 to 15 for a zone-specific officer. Leave out for all zones.")
    add.set_defaults(func=cmd_add_officer)

    listing = commands.add_parser("list-officers", help="List officer accounts.")
    listing.set_defaults(func=cmd_list_officers)

    pending = commands.add_parser("list-pending", help="List officer sign-ups waiting for approval.")
    pending.set_defaults(func=cmd_list_pending)

    approve = commands.add_parser("approve-officer", help="Approve an officer sign-up so it can log in.")
    approve.add_argument("--username", required=True)
    approve.set_defaults(func=cmd_approve_officer)

    check = commands.add_parser("check-overdue", help="Escalate complaints whose time limit has passed.")
    check.set_defaults(func=cmd_check_overdue)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except sqlite3.Error as error:
        raise SystemExit(f"Database error: {error}") from error


if __name__ == "__main__":
    main()
