"""Tests for the complaint router coded tools and the agent network file.

No LLM or network is needed. These tests use the charter data file in data/.
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "complaint_tools"))

# pylint: disable=wrong-import-position
from complaintrouter.charter_lookup import CharterLookup, lookup_timeline  # noqa: E402
from complaintrouter.common import load_charter  # noqa: E402
from complaintrouter.escalation import EscalationChecker, escalation_status  # noqa: E402
from complaintrouter.intake import ComplaintIntake, classify_complaint  # noqa: E402
from complaintrouter.reply import BANNER, ReplyDrafter, build_reply  # noqa: E402
from complaintrouter.router import ComplaintRouter, route  # noqa: E402


def run(tool, args):
    """Call a CodedTool's async_invoke and decode its JSON reply."""
    return json.loads(asyncio.run(tool.async_invoke(args, {})))


CHARTER = load_charter()


def test_leak_in_transmission_main_gets_seven_days():
    result = classify_complaint("Big leak in the transmission main near the bus stop")
    assert result["complaint_type"] == "water_leakage"
    assert result["subtype"] == "transmission_main"
    timeline = lookup_timeline("water_leakage", "transmission_main", CHARTER)
    assert timeline["fix_days"] == 7


def test_leak_without_location_uses_shortest_deadline_and_notes_it():
    result = classify_complaint("Water leaking from the pipe near my house")
    assert result["complaint_type"] == "water_leakage"
    assert result["subtype"] == "service_line"
    assert any("Leak location not stated" in note for note in result["notes"])


def test_contaminated_water_with_child_sick_is_urgent():
    result = classify_complaint("Contaminated water, my child is sick with fever")
    assert result["complaint_type"] == "water_pollution"
    assert result["urgent"] is True


def test_sewer_main_blockage_gets_four_days():
    result = classify_complaint("Sewer main blocked, manhole overflow on our street")
    assert result["complaint_type"] in ("sewer_main_blockage",)
    assert lookup_timeline("sewer_main_blockage", None, CHARTER)["fix_days"] == 4


def test_unsafe_cleaning_is_always_urgent_and_goes_to_helpline():
    result = classify_complaint("Workers died while cleaning the septic tank without safety gear")
    assert result["complaint_type"] == "unsafe_cleaning"
    assert result["urgent"] is True
    assert route("unsafe_cleaning", CHARTER)["owner_key"] == "national_helpline_14420"


def test_tax_complaint_has_no_maintenance_timeline_and_uses_matrix():
    result = classify_complaint("My water bill is wrong, the excess bill must be corrected")
    assert result["complaint_type"] == "tax_charges"
    timeline = lookup_timeline("tax_charges", None, CHARTER)
    assert timeline["fix_days"] is None
    assert route("tax_charges", CHARTER)["escalation_key"] == "tax_charges"


def test_general_grievance_only_when_nothing_specific_matches():
    result = classify_complaint("I want to file a grievance about the staff behaviour")
    assert result["complaint_type"] == "general_grievance"
    assert route("general_grievance", CHARTER)["owner_key"] == "grievance_cell"


def test_tie_between_two_types_needs_human_review():
    result = classify_complaint("Leak and the tanker has not come")
    assert result["needs_human_review"] is True
    assert any("Tie" in note for note in result["notes"])


def test_unknown_complaint_is_unclassified_for_human():
    result = classify_complaint("Lovely weather in the city today")
    assert result["complaint_type"] == "unclassified"
    assert result["needs_human_review"] is True


def test_intake_tool_returns_json():
    result = run(ComplaintIntake(), {"complaint_text": "No water supply since morning"})
    assert result["complaint_type"] == "no_water_supply"


def test_charter_tool_reports_source_label():
    result = run(CharterLookup(), {"complaint_type": "new_connection_delay"})
    assert result["fix_days"] == 15
    assert result["label_source"].startswith("CMWSSB Citizen's Charter 2021")


def test_escalation_reports_printed_days_and_names_no_current_level():
    row = escalation_status("water_network", 10, CHARTER)
    assert row["current_level_stated"] is False
    assert "current_stage" not in row
    assert "next_escalation_day" not in row
    assert [level["days"] for level in row["levels_as_printed"]] == [3, 2, 2, 2]


def test_escalation_says_cumulative_is_not_stated():
    row = escalation_status("new_connection", None, CHARTER)
    assert "does not state whether these days are cumulative" in row["note"]
    assert [level["days"] for level in row["levels_as_printed"]] == [7, 4, 3, 2]


def test_escalation_tool_treats_missing_days_as_not_given():
    result = run(EscalationChecker(), {"escalation_key": "water_network"})
    assert result["days_elapsed"] is None
    assert result["current_level_stated"] is False


def test_escalation_not_applicable_for_helpline_type():
    result = escalation_status(None, 3, CHARTER)
    assert result["applies"] is False


def test_escalation_tool_accepts_empty_key():
    result = run(EscalationChecker(), {"escalation_key": "", "days_elapsed": 2})
    assert result["applies"] is False


def test_router_tool_names_depot_for_leakage():
    result = run(ComplaintRouter(), {"complaint_type": "water_leakage"})
    assert result["owner_key"] == "depot"
    assert "Depot Engineer" in result["owner"]


def test_reply_always_starts_with_draft_banner_and_never_claims_sent():
    text = build_reply({"label": "Water leakage", "owner": "Depot", "fix_days": 3}, CHARTER)
    assert text.startswith(BANNER)
    assert "NOT SENT" in text
    assert "has been sent" not in text.lower()


def test_reply_flags_passed_timeline():
    text = build_reply({"label": "Sewer main blockage", "owner": "Depot", "fix_days": 4, "days_elapsed": 10}, CHARTER)
    assert "has passed (10 days since registration)" in text


def test_reply_tool_includes_reviewer_notes():
    result = run(ReplyDrafter(), {
        "label": "Water leakage",
        "owner": "Depot",
        "fix_days": 3,
        "review_notes": json.dumps(["Leak location not stated."]),
    })
    assert "Leak location not stated." in result["draft_reply"]


def test_charter_timeline_values_match_verified_tables():
    """Spot-check values that were re-read from the charter's tables."""
    assert lookup_timeline("water_leakage", "service_line", CHARTER)["fix_days"] == 3
    assert lookup_timeline("water_leakage", "distribution_main", CHARTER)["fix_days"] == 5
    assert lookup_timeline("water_pollution", "not_identified", CHARTER)["fix_days"] == 15
    assert lookup_timeline("handpump_repair", "india_mark_pump", CHARTER)["fix_days"] == 5
    assert lookup_timeline("damaged_sewer_line", None, CHARTER)["fix_days"] == 20
    assert lookup_timeline("street_water_no_piped", None, CHARTER)["fix_hours"] == 4
    assert CHARTER["escalation_matrix"]["new_connection"] == {
        "depot": 7, "deputy_ae": 4, "area_engineer": 3, "superintendent_engineer": 2}


def test_hocon_names_resolve_to_real_classes():
    """Every agent class in the network must point at a module and class that exist."""
    from pyhocon import ConfigFactory  # pylint: disable=import-outside-toplevel

    config = ConfigFactory.parse_file(str(ROOT / "registries" / "complaintrouter.hocon"))
    agents = {tool["name"]: tool for tool in config["tools"]}
    assert config["tools"][0]["name"] == "complaint_coordinator"
    for name in config["tools"][0]["tools"]:
        assert name in agents, f"front man calls unknown agent {name}"
        module_name, class_name = agents[name]["class"].split(".")
        module = __import__(f"complaintrouter.{module_name}", fromlist=[class_name])
        assert hasattr(module, class_name), f"{class_name} missing in {module_name}"


def test_reply_names_charter_source_and_escalation_as_printed():
    text = build_reply({"label": "Water leakage in a pipe (service line)", "owner": "Depot",
                        "fix_days": 3, "escalation_key": "water_network"}, CHARTER)
    assert "Source: CMWSSB Citizen's Charter 2021, PDF copy" in text
    assert "Charter timeline for repair: 3 days" in text
    assert "Depot Engineer or Senior Accounts Officer: 3 days" in text
    assert "Superintendent Engineer: 2 days" in text
    assert "does not state whether these days are cumulative" in text


def test_reply_tool_takes_escalation_key_and_days_as_text():
    result = run(ReplyDrafter(), {
        "label": "Sewer main blockage", "owner": "Depot", "fix_days": 4,
        "escalation_key": "sewer_network", "days_elapsed": "10",
    })
    assert "has passed (10 days since registration)" in result["draft_reply"]
    assert "Area Engineer: 2 days" in result["draft_reply"]


def test_reply_without_escalation_key_has_no_escalation_section():
    text = build_reply({"label": "General grievance", "owner": "Grievance Cell"}, CHARTER)
    assert "Escalation days" not in text
