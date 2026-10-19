"""Local LLM classifier for the offline app.

The model (llama3.1 through a local Ollama server) reads the citizen's wording and
picks a charter complaint type and subtype. It never writes timelines, owners,
escalation days or reply text. Those come from data/charter.json through the coded tools.

Every answer is checked against charter.json. If Ollama is not running, or the answer
is not a valid charter choice, the keyword classifier in intake.py is used instead.
Urgency always comes from the keyword classifier, so the model cannot lower it.
"""

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from .common import load_charter
from .intake import classify_complaint

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1"
DEFAULT_TIMEOUT_SECONDS = 120


def ollama_settings() -> Dict[str, Any]:
    """Read the Ollama address, model and timeout from the environment, with defaults."""
    return {
        "base_url": os.environ.get("COMPLAINTROUTER_OLLAMA_URL", DEFAULT_OLLAMA_URL),
        "model": os.environ.get("COMPLAINTROUTER_MODEL", DEFAULT_MODEL),
        "timeout": float(os.environ.get("COMPLAINTROUTER_LLM_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)),
    }


def build_prompt(complaint: str, charter: Dict[str, Any]) -> str:
    """Return the instruction and the list of allowed charter types for the model."""
    lines = [
        "You classify a citizen's water or sewer complaint for Chennai's water board.",
        "Choose exactly one complaint_type from the list below, based on the main problem.",
        "Choose a subtype only if the type lists subtypes; otherwise use null.",
        "If no type fits, use general_grievance. Do not invent types or subtypes.",
        'Answer with JSON only, in this form: {"complaint_type": "...", "subtype": "..." or null}',
        "",
        "Allowed types:",
    ]
    for key, entry in charter["complaint_types"].items():
        subtypes = entry.get("subtypes")
        if subtypes:
            lines.append(f"- {key}: {entry['label']}. Subtypes: {', '.join(subtypes)}")
        else:
            lines.append(f"- {key}: {entry['label']}")
    lines += ["", "Complaint:", complaint.strip(), "", "JSON:"]
    return "\n".join(lines)


def parse_llm_answer(raw: Optional[str], charter: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a valid charter choice, or None when the answer cannot be used.

    An unknown or missing subtype is returned as None, so the caller can apply the default and say so.
    """
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    complaint_type = data.get("complaint_type")
    if not isinstance(complaint_type, str) or complaint_type not in charter["complaint_types"]:
        return None

    entry = charter["complaint_types"][complaint_type]
    subtype = data.get("subtype")
    if entry.get("subtypes"):
        subtype = subtype if isinstance(subtype, str) and subtype in entry["subtypes"] else None
    else:
        subtype = None
    return {"complaint_type": complaint_type, "subtype": subtype}


def ask_ollama(prompt: str, settings: Dict[str, Any]) -> Optional[str]:
    """Send the prompt to the local Ollama server. Return the model's text, or None if unreachable."""
    body = json.dumps({
        "model": settings["model"],
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }).encode("utf-8")
    request = urllib.request.Request(
        settings["base_url"].rstrip("/") + "/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings["timeout"]) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    text = payload.get("response") if isinstance(payload, dict) else None
    return text if isinstance(text, str) else None


def _merge(keyword: Dict[str, Any], choice: Dict[str, Any], charter: Dict[str, Any], model: str) -> Dict[str, Any]:
    """Combine the model's valid choice with the keyword result (urgency and matched terms)."""
    complaint_type = choice["complaint_type"]
    entry = charter["complaint_types"][complaint_type]
    notes = [f"Type chosen by the local LLM ({model}). Confirm it matches the complaint."]

    subtype = choice["subtype"]
    if entry.get("subtypes") and subtype is None:
        subtype = entry["default_subtype"]
        notes.append(f"Subtype not stated; defaulted to {subtype}. Confirm before relying on the deadline.")
        if complaint_type == "water_leakage":
            notes.append("Leak location not stated. The shortest deadline (service line) is used.")

    keyword_type = keyword["complaint_type"]
    if keyword_type != complaint_type:
        keyword_label = charter["complaint_types"].get(keyword_type, {}).get("label", keyword_type)
        notes.append(f"The keyword classifier chose: {keyword_label}. Confirm the type.")

    urgent = bool(keyword["urgent"]) or bool(entry.get("always_urgent"))
    return {
        "complaint_type": complaint_type,
        "subtype": subtype,
        "urgent": urgent,
        "matched_terms": keyword["matched_terms"],
        "needs_human_review": True,
        "notes": notes,
        "classifier": "llm",
        "llm_status": f"Type and subtype chosen by the local LLM ({model}).",
    }


def classify(complaint: str, use_llm: bool = True, settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Classify a complaint with the local LLM when requested, falling back to keywords."""
    charter = load_charter()
    keyword = classify_complaint(complaint)
    fallback = dict(keyword, classifier="keyword")

    if not use_llm:
        fallback["llm_status"] = "Not requested; keyword classifier used."
        return fallback

    settings = settings or ollama_settings()
    raw = ask_ollama(build_prompt(complaint, charter), settings)
    if raw is None:
        fallback["llm_status"] = (
            f"Local LLM not reachable at {settings['base_url']}; keyword classifier used."
        )
        return fallback

    choice = parse_llm_answer(raw, charter)
    if choice is None:
        fallback["llm_status"] = "Local LLM answer was not a valid charter type; keyword classifier used."
        return fallback

    return _merge(keyword, choice, charter, settings["model"])
