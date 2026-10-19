"""Field and stage rules for the complaint portal.

Each charter complaint type belongs to one field (water supply, sewerage, and so on).
A complaint goes to the owning depot first. If it is not resolved in time, it moves up
the charter's escalation levels, and the last level is the District Head Office.

A citizen who says the problem is not fixed is treated differently: the complaint goes to
the ward's office (the depot officer for the ward's zone) with the same time to fix it as the
depot had, and then to the District Head Office if the ward office does not fix it in time.

The time limit at each level comes from data/charter.json. The charter does not say
whether its escalation days are cumulative or per level. This portal treats them as per
level, as the charter's table reads. CMWSSB should confirm this before real use.
"""

from datetime import timedelta
from typing import Any, Dict, List, Optional

FIELDS: Dict[str, str] = {
    "water": "Water supply",
    "sewerage": "Sewerage",
    "billing": "Billing and charges",
    "new_connection": "New connections",
    "general": "General grievances",
}

FIELD_FOR_TYPE: Dict[str, str] = {
    "water_leakage": "water",
    "water_pollution": "water",
    "no_water_supply": "water",
    "defective_meter": "water",
    "handpump_repair": "water",
    "street_water_no_piped": "water",
    "tanker_supply": "water",
    "sewer_main_blockage": "sewerage",
    "house_sewer_blockage": "sewerage",
    "damaged_sewer_line": "sewerage",
    "septic_tank_clearance": "sewerage",
    "unsafe_cleaning": "sewerage",
    "tax_charges": "billing",
    "new_connection_delay": "new_connection",
    "general_grievance": "general",
}

DEPOT = "depot"
DISTRICT_HEAD = "district_head"
FIELD_ALL = "all"
DISTRICT_HEAD_LABEL = "District Head Office"
STAGES: List[str] = [DEPOT, "deputy_ae", "area_engineer", "superintendent_engineer", DISTRICT_HEAD]

# The ward office is a stage, not an officer level. Its officer is the depot officer for the
# ward's zone, so it is looked up at the depot level.
WARD = "ward"
WARD_LABEL = "Ward office"

OPEN = "open"
AWAITING = "awaiting_confirmation"
CLOSED = "closed"
STATUS_TEXT: Dict[str, str] = {
    OPEN: "Open. Being handled.",
    AWAITING: "Marked resolved. Waiting for the citizen to confirm.",
    CLOSED: "Closed. The citizen confirmed the problem is fixed.",
}


def field_for(complaint_type: str) -> str:
    """Return the field key for a charter complaint type. Unknown types go to general grievances."""
    return FIELD_FOR_TYPE.get(complaint_type, "general")


def stage_path(escalation_key: Optional[str]) -> List[str]:
    """Return the levels a complaint moves through. Types with no charter escalation go straight to the District Head Office."""
    if escalation_key:
        return list(STAGES)
    return [DEPOT, DISTRICT_HEAD]


def path_after_citizen_not_fixed(path: List[str], stage: str) -> List[str]:
    """Return the new route when the citizen says the problem is not fixed.

    The route so far is kept. The ward office comes next, then the District Head Office. A complaint
    already at the ward office goes straight to the District Head Office. A complaint already at the
    District Head Office has nowhere further to go, so the route is unchanged.
    """
    index = path.index(stage)
    if stage == DISTRICT_HEAD:
        return list(path)
    if stage == WARD:
        return path[: index + 1] + [DISTRICT_HEAD]
    return path[: index + 1] + [WARD, DISTRICT_HEAD]


def officer_level_for(stage: str) -> str:
    """Return the officer level whose account handles a stage. The ward office uses the depot officers."""
    return DEPOT if stage == WARD else stage


def level_name(level: str, charter: Dict[str, Any]) -> str:
    """Return the readable name of a stage or officer level."""
    if level == DISTRICT_HEAD:
        return DISTRICT_HEAD_LABEL
    if level == WARD:
        return WARD_LABEL
    return charter["stage_labels"][level]


def stage_label(stage: str, charter: Dict[str, Any], owner_label: str) -> str:
    """Return the readable name of the office a complaint is at. The depot uses the charter owner."""
    if stage == DEPOT:
        return owner_label
    return level_name(stage, charter)


def stage_window(
    fix_days: Optional[int],
    fix_hours: Optional[int],
    escalation_key: Optional[str],
    stage: str,
    charter: Dict[str, Any],
) -> Optional[timedelta]:
    """Return how long a stage has before it escalates. None means no time limit applies.

    The ward office has the same time to fix the problem as the depot had, from the charter's timeline.
    """
    if stage == DISTRICT_HEAD:
        return None
    if stage in (DEPOT, WARD):
        if fix_days is not None:
            return timedelta(days=fix_days)
        if fix_hours is not None:
            return timedelta(hours=fix_hours)
    if stage == WARD:
        return None
    if escalation_key:
        days = charter["escalation_matrix"][escalation_key].get(stage)
        if days is not None:
            return timedelta(days=days)
    return None
