"""Creates demo officer accounts: one per field and level, plus the District Head Office.

Usernames look like water.depot, sewerage.deputy_ae, and district.head. Change the
passwords before any real use.
"""

from typing import List

from complaintrouter.common import load_charter
from complaint_portal.auth import hash_password
from complaint_portal.rules import DEPOT, DISTRICT_HEAD, DISTRICT_HEAD_LABEL, FIELD_ALL, FIELDS, level_name
from complaint_portal.store import Store

FIELD_KEYS = list(FIELDS)
LEVEL_KEYS = [DEPOT, "deputy_ae", "area_engineer", "superintendent_engineer"]


def seed_demo_officers(store: Store, password: str) -> List[str]:
    """Create the demo accounts that do not exist yet. Return the usernames created."""
    if len(password) < 8:
        raise ValueError("Use a password of at least 8 characters.")
    charter = load_charter()
    accounts = [
        (f"{field}.{level}", f"{FIELDS[field]}: {level_name(level, charter)}", field, level)
        for field in FIELD_KEYS
        for level in LEVEL_KEYS
    ]
    accounts.append(("district.head", DISTRICT_HEAD_LABEL, FIELD_ALL, DISTRICT_HEAD))

    created = []
    for username, name, field, level in accounts:
        if store.get_officer_by_username(username) is not None:
            continue
        store.insert_officer(username, name, field, level, hash_password(password))
        created.append(username)
    return created
