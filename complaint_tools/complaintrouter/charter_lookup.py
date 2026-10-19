"""Looks up the charter timeline for a complaint type and subtype.

Returns the maintenance deadline when the charter gives one. The escalation
schedule is handled separately in escalation.py.
"""

import json
from typing import Any, Dict, Optional

from neuro_san.interfaces.coded_tool import CodedTool

from .common import load_charter


def lookup_timeline(complaint_type: str, subtype: Optional[str], charter: Dict[str, Any]) -> Dict[str, Any]:
    """Return the fix deadline for a complaint, or a clear note when none exists."""
    entry = charter["complaint_types"].get(complaint_type)
    if entry is None:
        return {"complaint_type": complaint_type, "found": False, "fix_days": None, "fix_hours": None,
                "fix_note": "Unknown complaint type. No charter timeline applies."}

    defaulted = False
    if entry.get("subtypes"):
        if subtype not in entry["subtypes"]:
            defaulted = True
            subtype = entry["default_subtype"]
        sub = entry["subtypes"][subtype]
        fix_days = sub.get("fix_days")
        fix_hours = sub.get("fix_hours")
        label = f"{entry['label']} ({sub['label']})"
    else:
        fix_days = entry.get("fix_days")
        fix_hours = entry.get("fix_hours")
        label = entry["label"]

    return {
        "complaint_type": complaint_type,
        "found": True,
        "label": label,
        "subtype_used": subtype,
        "subtype_defaulted": defaulted,
        "fix_days": fix_days,
        "fix_hours": fix_hours,
        "fix_note": entry.get("fix_note", ""),
        "charter_row": entry.get("charter_row", ""),
    }


class CharterLookup(CodedTool):
    """CodedTool that returns the charter timeline for a complaint."""

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        charter = load_charter()
        subtype = args.get("subtype")
        result = lookup_timeline(str(args.get("complaint_type", "")), subtype if subtype else None, charter)
        result["label_source"] = charter["label"]
        return json.dumps(result)
