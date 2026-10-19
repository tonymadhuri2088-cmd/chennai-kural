"""Runs the complaint router steps in order without an LLM.

Usage (from the project root):
    python examples/run_pipeline.py
        Runs the sample sewer complaint, registered 10 days ago.

    python examples/run_pipeline.py "Water is leaking from the pipe near my house" --days 3
        Runs any complaint. Pass --days only if the citizen gave days since registration.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "complaint_tools"))

# pylint: disable=wrong-import-position
from complaintrouter.charter_lookup import CharterLookup  # noqa: E402
from complaintrouter.intake import ComplaintIntake  # noqa: E402
from complaintrouter.reply import ReplyDrafter  # noqa: E402
from complaintrouter.router import ComplaintRouter  # noqa: E402

SAMPLE_COMPLAINT = "Sewer main blocked, manhole overflowing on our street, no action in 10 days"
SAMPLE_DAYS = 10


async def call(tool, args):
    """Invoke a CodedTool and decode its JSON reply."""
    return json.loads(await tool.async_invoke(args, {}))


async def run(complaint, days_elapsed):
    """Run the five steps for one complaint and print the exact draft reply."""
    intake = await call(ComplaintIntake(), {"complaint_text": complaint})
    timeline = await call(CharterLookup(), {"complaint_type": intake["complaint_type"], "subtype": intake["subtype"] or ""})
    route = await call(ComplaintRouter(), {"complaint_type": intake["complaint_type"]})
    reply = await call(ReplyDrafter(), {
        "reference": "REF-DEMO",
        "label": timeline["label"],
        "owner": route["owner"],
        "fix_days": timeline["fix_days"],
        "fix_hours": timeline["fix_hours"],
        "fix_note": timeline["fix_note"],
        "days_elapsed": days_elapsed,
        "urgent": intake["urgent"],
        "escalation_key": route.get("escalation_key") or "",
        "review_notes": json.dumps(intake["notes"]),
    })

    print("INTAKE:", intake)
    print("TIMELINE:", timeline["label"], "| fix days:", timeline["fix_days"])
    print("ROUTE:", route["owner"])
    print()
    print(reply["draft_reply"])


def main():
    parser = argparse.ArgumentParser(description="Run the complaint router without an LLM.")
    parser.add_argument("complaint", nargs="?",
                        help="Complaint text. Leave out to run the sample sewer complaint.")
    parser.add_argument("--days", type=float, default=None,
                        help="Days since registration, only if the citizen gave them.")
    args = parser.parse_args()

    if args.complaint is None:
        complaint, days_elapsed = SAMPLE_COMPLAINT, SAMPLE_DAYS
    else:
        complaint, days_elapsed = args.complaint, args.days
    asyncio.run(run(complaint, days_elapsed))


if __name__ == "__main__":
    main()
