"""Routes a complaint to the owning unit named in the charter."""

import json
from typing import Any, Dict

from neuro_san.interfaces.coded_tool import CodedTool

from .common import load_charter


def route(complaint_type: str, charter: Dict[str, Any]) -> Dict[str, Any]:
    """Return the owner and escalation key for a complaint type."""
    entry = charter["complaint_types"].get(complaint_type)
    if entry is None:
        return {"found": False, "owner": None, "escalation_key": None}
    return {
        "found": True,
        "owner_key": entry["owner"],
        "owner": charter["owners"][entry["owner"]],
        "escalation_key": entry.get("escalation_key"),
        "helpline_for_urgent": charter["helplines"]["complaint_cell_24x7"],
    }


class ComplaintRouter(CodedTool):
    """CodedTool that names the owning unit for a complaint."""

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        charter = load_charter()
        return json.dumps(route(str(args.get("complaint_type", "")), charter))
