"""Classifies a citizen complaint into a charter complaint type and subtype.

This is a keyword classifier, not a trained model. It returns notes whenever a
subtype or timeline had to be assumed, so a human can confirm before action.
"""

import json
from typing import Any, Dict, List

from neuro_san.interfaces.coded_tool import CodedTool

from .common import load_charter

# Specific types. "general_grievance" is used only when none of these match.
TYPE_KEYWORDS = {
    "unsafe_cleaning": ["manual scavenging", "unsafe cleaning", "cleaning sewer without", "died while cleaning", "without safety gear"],
    "water_leakage": ["leak", "pipe burst", "pipeline burst", "water wastage", "water flowing on the road", "water flowing on road"],
    "water_pollution": ["contaminated", "dirty water", "polluted", "muddy water", "smelly water", "sewage in water", "water quality", "discoloured water", "discolored water"],
    "no_water_supply": ["no water", "no supply", "water not coming", "water supply stopped", "defective water supply", "defective supply"],
    "defective_meter": ["water meter", "meter defective", "meter faulty", "meter not working", "meter stopped"],
    "handpump_repair": ["hand pump", "handpump", "india mark"],
    "sewer_main_blockage": ["sewer main", "main sewer", "sewer blocked", "sewer blockage", "manhole overflow", "sewage overflow", "sewer overflow"],
    "house_sewer_blockage": ["house sewer", "house drain", "toilet blocked", "drain blocked at home", "toilet not flushing"],
    "damaged_sewer_line": ["sewer line damaged", "damaged sewer", "broken sewer", "sewer pipe broken", "sewer line broken"],
    "tax_charges": ["water bill", "tax", "charges", "arrears", "bill is wrong", "payment not reflected", "excess bill"],
    "tanker_supply": ["tanker", "water lorry"],
    "new_connection_delay": ["new connection", "connection not given", "application pending", "connection pending"],
    "street_water_no_piped": ["no piped", "public tap", "street water", "no pipe connection", "standpipe"],
    "septic_tank_clearance": ["septic", "desludging", "tank clearance", "tank cleaning"],
}

GENERAL_KEYWORDS = ["complaint", "grievance", "vigilance", "corruption", "employee", "rude"]

URGENT_TERMS = [
    "died", "death", "collapse", "child", "injury", "injured", "electrocut", "sick",
    "hospital", "fever", "diarrhoea", "diarrhea", "vomit", "contaminated", "unsafe",
    "manhole",
]


def _subtype(complaint_type: str, text: str) -> Dict[str, Any]:
    """Pick a subtype from the text. Report whether it was stated or assumed."""
    lowered = text.lower()
    if complaint_type == "water_leakage":
        if "transmission" in lowered:
            return {"subtype": "transmission_main", "stated": True}
        if "distribution" in lowered or " main" in lowered:
            return {"subtype": "distribution_main", "stated": True}
        if "service" in lowered:
            return {"subtype": "service_line", "stated": True}
        return {"subtype": "service_line", "stated": False}
    if complaint_type == "water_pollution":
        if any(term in lowered for term in ["not identified", "unknown source", "cannot find", "source unknown"]):
            return {"subtype": "not_identified", "stated": True}
        if any(term in lowered for term in ["at the tap", "from the tap", "pipe", "tank"]):
            return {"subtype": "identified_point", "stated": True}
        return {"subtype": "identified_point", "stated": False}
    if complaint_type == "handpump_repair":
        if "india mark" in lowered:
            return {"subtype": "india_mark_pump", "stated": True}
        return {"subtype": "hand_pump", "stated": "hand pump" in lowered or "handpump" in lowered}
    return {"subtype": None, "stated": True}


def classify_complaint(text: str) -> Dict[str, Any]:
    """Return the complaint type, subtype, urgency, and any notes for a human."""
    charter = load_charter()
    lowered = text.lower()
    urgent_hits = [term for term in URGENT_TERMS if term in lowered]
    matches: Dict[str, List[str]] = {}
    for complaint_type, terms in TYPE_KEYWORDS.items():
        hits = [term for term in terms if term in lowered]
        if hits:
            matches[complaint_type] = hits

    notes: List[str] = []
    if not matches:
        general = [term for term in GENERAL_KEYWORDS if term in lowered]
        if general:
            complaint_type, hits = "general_grievance", general
        else:
            return {
                "complaint_type": "unclassified", "subtype": None, "urgent": bool(urgent_hits),
                "matched_terms": [], "needs_human_review": True,
                "notes": ["No charter complaint type matched."],
            }
    else:
        ranked = sorted(matches.items(), key=lambda item: len(item[1]), reverse=True)
        complaint_type, hits = ranked[0]
        if len(ranked) > 1 and len(ranked[1][1]) == len(hits):
            notes.append(f"Tie between {complaint_type} and {ranked[1][0]}; confirm the type.")

    entry = charter["complaint_types"][complaint_type]
    subtype_info = _subtype(complaint_type, text)
    subtype = subtype_info["subtype"]
    if entry.get("subtypes") and not subtype_info["stated"]:
        notes.append(f"Subtype not stated; defaulted to {subtype}. Confirm before relying on the deadline.")
    if complaint_type == "water_leakage" and not subtype_info["stated"]:
        notes.append("Leak location not stated. The shortest deadline (service line) is used.")

    urgent = bool(urgent_hits) or bool(entry.get("always_urgent"))
    return {
        "complaint_type": complaint_type,
        "subtype": subtype,
        "urgent": urgent,
        "matched_terms": hits,
        "needs_human_review": bool(notes) or urgent,
        "notes": notes,
    }


class ComplaintIntake(CodedTool):
    """CodedTool that classifies one complaint."""

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        return json.dumps(classify_complaint(str(args.get("complaint_text", ""))))
