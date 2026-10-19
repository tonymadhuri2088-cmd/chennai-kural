"""Drafts a reply to a citizen. The draft is never sent and is never an official CMWSSB reply."""

import json
from typing import Any, Dict, List

from neuro_san.interfaces.coded_tool import CodedTool

from .common import load_charter, parse_arg
from .escalation import escalation_status, parse_days

BANNER = (
    "DRAFT - NOT SENT - NOT AN OFFICIAL CMWSSB REPLY - "
    "FOR REVIEW BY THE BOARD BEFORE ANY USE"
)


def build_reply(data: Dict[str, Any], charter: Dict[str, Any]) -> str:
    """Return the complete draft reply text with the fixed banner first."""
    lines: List[str] = [BANNER, ""]
    reference = data.get("reference") or "(reference to be assigned)"
    lines.append(f"Source: {charter['label']}")
    lines.append(f"Complaint reference: {reference}")
    lines.append(f"Complaint: {data.get('label', 'not stated')}")
    lines.append(f"Forwarded to: {data.get('owner', 'to be assigned')}")
    if data.get("fix_days"):
        lines.append(f"Charter timeline for repair: {data['fix_days']} days")
        if data.get("days_elapsed") is not None and data["days_elapsed"] > data["fix_days"]:
            lines.append(f"The charter timeline of {data['fix_days']} days has passed ({data['days_elapsed']} days since registration).")
    elif data.get("fix_hours"):
        lines.append(f"Charter timeline for repair: {data['fix_hours']} hours")
    else:
        lines.append("Charter timeline for repair: none stated for this complaint type")
    if data.get("fix_note"):
        lines.append(f"Note: {data['fix_note']}")
    if data.get("escalation_key") in charter["escalation_matrix"]:
        status = escalation_status(data["escalation_key"], None, charter)
        lines.append("")
        lines.append("Escalation days as printed in the charter, per officer level:")
        for level in status["levels_as_printed"]:
            lines.append(f"  {level['level']}: {level['days']} days")
        lines.append(status["after_last_level"])
        lines.append(status["note"])
    lines.append("")
    if data.get("urgent"):
        lines.append(f"If anyone is at immediate risk, call the 24x7 complaint cell on {charter['helplines']['complaint_cell_24x7']}.")
    lines.append(
        f"For follow-up, call toll free {charter['helplines']['toll_free']} or the 24x7 complaint cell on "
        f"{charter['helplines']['complaint_cell_24x7']}."
    )
    if data.get("review_notes"):
        lines.append("")
        lines.append("Open items for the reviewer:")
        lines += [f"  - {note}" for note in data["review_notes"]]
    return "\n".join(lines)


class ReplyDrafter(CodedTool):
    """CodedTool that returns the complete draft reply text."""

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        charter = load_charter()
        days = parse_days(args.get("days_elapsed"))
        if days is not None and days.is_integer():
            days = int(days)
        data = {
            "reference": args.get("reference"),
            "label": args.get("label"),
            "owner": args.get("owner"),
            "fix_days": parse_arg(args.get("fix_days"), None),
            "fix_hours": parse_arg(args.get("fix_hours"), None),
            "fix_note": args.get("fix_note") or "",
            "days_elapsed": days,
            "urgent": str(args.get("urgent", "false")).lower() in ("true", "1", "yes"),
            "review_notes": parse_arg(args.get("review_notes"), []),
            "escalation_key": args.get("escalation_key") or None,
        }
        return json.dumps({"draft_reply": build_reply(data, charter)})
