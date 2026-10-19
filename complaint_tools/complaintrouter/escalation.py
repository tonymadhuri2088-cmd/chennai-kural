"""Reports the charter escalation schedule for a complaint.

The charter's escalation matrix gives a number of days for each officer level.
The charter does not say whether those numbers are cumulative from registration
or apply to each level separately. So this tool reports the days exactly as
printed. It does not name a current officer level or a date for the next
escalation.
"""

import json
from typing import Any, Dict, Optional

from neuro_san.interfaces.coded_tool import CodedTool

from .common import load_charter

NOT_STATED = (
    "The charter does not state whether these days are cumulative from registration "
    "or apply to each level separately. No current level or escalation date is given."
)


def escalation_status(matrix_key: Optional[str], days_elapsed: Optional[float], charter: Dict[str, Any]) -> Dict[str, Any]:
    """Return the charter's per-level days for a complaint type, without naming a current level."""
    if matrix_key is None:
        return {"applies": False, "reason": "The charter gives no escalation matrix for this complaint type."}

    row = charter["escalation_matrix"][matrix_key]
    levels = [
        {"level": charter["stage_labels"][stage], "days": row[stage]}
        for stage in charter["stage_order"]
    ]
    return {
        "applies": True,
        "levels_as_printed": levels,
        "after_last_level": "If not solved, a notification goes to the Chief Engineer (charter p. 4).",
        "days_elapsed": days_elapsed,
        "current_level_stated": False,
        "note": NOT_STATED,
    }


def parse_days(raw: Any) -> Optional[float]:
    """Return days elapsed as a number, or None when the user did not give it."""
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


class EscalationChecker(CodedTool):
    """CodedTool that reports the charter's escalation levels for a complaint."""

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        charter = load_charter()
        matrix_key = args.get("escalation_key") or None
        days = parse_days(args.get("days_elapsed"))
        result = escalation_status(matrix_key, days, charter)
        result["label_source"] = charter["label"]
        return json.dumps(result, default=str)
