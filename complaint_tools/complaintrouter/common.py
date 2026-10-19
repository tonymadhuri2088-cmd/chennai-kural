"""Shared helpers for the complaint router coded tools.

Every timeline comes from data/charter.json, which carries its own source label.
Set COMPLAINTROUTER_DATA_DIR to point at a different data folder.
"""

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def data_dir() -> Path:
    """Return the folder that holds the charter data."""
    return Path(os.environ.get("COMPLAINTROUTER_DATA_DIR", DEFAULT_DATA_DIR))


def load_charter() -> Any:
    """Load the charter data file."""
    with open(data_dir() / "charter.json", encoding="utf-8") as handle:
        return json.load(handle)


def parse_arg(value: Any, default: Any) -> Any:
    """Accept a native value or a JSON string produced by an LLM."""
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def parse_bool(value: Any) -> bool:
    """Read a boolean that an LLM may have sent as text."""
    return str(value).strip().lower() in ("true", "1", "yes")
