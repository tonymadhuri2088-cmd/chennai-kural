"""Connects the router's output to the portal.

When a complaint is registered the portal runs the router (complaintrouter.pipeline). The router gives back
a message for the citizen and a timeline: the charter's repair time for this complaint and its escalation days
for each officer level. This module keeps the timeline with the complaint (snapshot) and turns it into the
progress steps the screens show (progress).

Nothing here is written by a model. The numbers come from data/charter.json through the router's own tools.
The router says the charter does not state whether its escalation days are cumulative or per level. The portal
treats them as per level (see rules.py), and the progress block says so.
"""

import json
from typing import Any, Dict, List, Optional

from complaintrouter.charter_lookup import lookup_timeline
from complaintrouter.escalation import escalation_status

from .rules import CLOSED, DEPOT, DISTRICT_HEAD, OPEN, WARD, stage_label


def snapshot(result: Dict[str, Any], charter: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the router's timeline for one complaint. result is what pipeline.run_complaint returned."""
    timeline = result["timeline"]
    escalation = result["escalation"]
    levels: List[Dict[str, Any]] = []
    if escalation.get("applies"):
        # The router lists its levels in the charter's stage order, so each one is matched to its stage here.
        for stage, item in zip(charter["stage_order"], escalation["levels_as_printed"]):
            levels.append({"stage": stage, "level": item["level"], "days": item["days"]})
    return {
        "label": timeline.get("label"),
        "fix_days": timeline.get("fix_days"),
        "fix_hours": timeline.get("fix_hours"),
        "fix_note": timeline.get("fix_note") or "",
        "applies": bool(escalation.get("applies")),
        "levels": levels,
        "after_last_level": escalation.get("after_last_level"),
        "note": escalation.get("note"),
    }


def snapshot_from_row(row: Dict[str, Any], charter: Dict[str, Any]) -> Dict[str, Any]:
    """The same timeline for a complaint filed before it was kept. It uses the router's tools, no model."""
    timeline = lookup_timeline(row.get("complaint_type") or "", row.get("subtype"), charter)
    escalation = escalation_status(row.get("escalation_key"), None, charter)
    return snapshot({"timeline": timeline, "escalation": escalation}, charter)


def _plural(count: Any, unit: str) -> str:
    number = int(count) if float(count).is_integer() else count
    return f"{number} {unit}" if number == 1 else f"{number} {unit}s"


def _fix_text(snap: Dict[str, Any]) -> Optional[str]:
    if snap.get("fix_days") is not None:
        return _plural(snap["fix_days"], "day")
    if snap.get("fix_hours") is not None:
        return _plural(snap["fix_hours"], "hour")
    return None


def _time_limit(stage: str, snap: Dict[str, Any], levels: Dict[str, Dict[str, Any]]) -> str:
    """The time this stage has, in words, taken from the router's timeline."""
    if stage == DISTRICT_HEAD:
        return "Final level. No time limit"
    if stage in (DEPOT, WARD):
        fix = _fix_text(snap)
        if fix is None and stage == DEPOT and DEPOT in levels:
            fix = _plural(levels[DEPOT]["days"], "day")
        if fix is None:
            return "No time stated in the charter"
        return f"{fix}, the same as the depot" if stage == WARD else fix
    if stage in levels:
        return _plural(levels[stage]["days"], "day")
    return "No time stated in the charter"


def progress(row: Dict[str, Any], charter: Dict[str, Any]) -> Dict[str, Any]:
    """The complaint's progress as the router's timeline lays it out, with the current stage marked.

    Each step: the office, the time the router's timeline gives it, and a state of done, current,
    upcoming or skipped (a stage a closed complaint never needed). The current step carries the
    live deadline the portal is counting down to.
    """
    raw = row.get("router_timeline")
    snap = json.loads(raw) if raw else snapshot_from_row(row, charter)
    path = json.loads(row["stage_path"]) if row.get("stage_path") else [DEPOT, DISTRICT_HEAD]
    current = row.get("stage") if row.get("stage") in path else path[0]
    position = path.index(current)
    closed = row.get("status") == CLOSED
    levels = {item["stage"]: item for item in snap.get("levels", [])}

    steps: List[Dict[str, Any]] = []
    for index, stage in enumerate(path):
        if index < position:
            state = "done"
        elif index == position:
            state = "done" if closed else "current"
        else:
            state = "skipped" if closed else "upcoming"
        step = {
            "stage": stage,
            "office": stage_label(stage, charter, row.get("owner_label") or "the field office"),
            "time_limit": _time_limit(stage, snap, levels),
            "state": state,
        }
        if state == "current" and row.get("status") == OPEN and row.get("stage_deadline"):
            step["deadline"] = row["stage_deadline"]
        steps.append(step)

    return {
        "label": snap.get("label"),
        "repair_time": _fix_text(snap),
        "fix_note": snap.get("fix_note") or "",
        "steps": steps,
        "after_last_level": snap.get("after_last_level"),
        "note": snap.get("note"),
        "kept_at_registration": bool(raw),
    }
