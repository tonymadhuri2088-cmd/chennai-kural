"""The two kinds of complaint the citizen chooses between on Register Complaint.

Emergency: urgent problems that need someone at once. No photos are asked for.
Not emergency (civic): everyday civic problems. Three photos are required.

The labels are shown exactly as the citizen sees them. The keys are stored in the database.
"""

from typing import Dict, List, Tuple

EMERGENCY = "emergency"
CIVIC = "civic"
KINDS = (EMERGENCY, CIVIC)
KIND_LABELS: Dict[str, str] = {EMERGENCY: "Emergency", CIVIC: "Not emergency"}

EMERGENCY_CATEGORIES: List[Tuple[str, str]] = [
    ("emergency_rescue", "Emergency Rescue"),
    ("fire_smoke", "Fire and smoke emergencies"),
    ("ambulance_medical", "Ambulance and medical emergencies"),
    ("lpg_leak", "LPG gas leakage"),
    ("hazardous_gas", "Hazardous gas or chemical leakage"),
    ("flood_rescue", "Flood rescue and evacuation"),
    ("building_collapse", "Building collapse and trapped persons"),
    ("electrical_hazard", "Electrical hazards and fallen live wires"),
    ("road_accident", "Road accidents requiring rescue"),
    ("lift_trapped", "People trapped in lifts or confined spaces"),
    ("tree_fall", "Tree falls blocking access or threatening lives"),
    ("drowning", "Drowning and water rescue"),
    ("landslide", "Landslides and structural hazards"),
]

CIVIC_CATEGORIES: List[Tuple[str, str]] = [
    ("water_supply", "Water Supply"),
    ("drainage_sewerage", "Drainage and Sewerage"),
    ("garbage_sanitation", "Garbage and Sanitation"),
    ("roads_footpaths", "Roads and Footpaths"),
    ("streetlights", "Streetlights"),
    ("flooding_waterlogging", "Flooding and Waterlogging"),
    ("public_health_strays", "Public Health and Stray Animals"),
    ("parks_infrastructure", "Parks and Public Infrastructure"),
    ("municipal_services_taxes", "Municipal Services and Taxes"),
    ("other_civic", "Other Complaints"),
]

PHOTOS_REQUIRED = 3
MAX_PHOTO_BYTES = 4 * 1024 * 1024
PHOTO_TYPES = ("image/jpeg", "image/png", "image/webp")


def categories_for(kind: str) -> List[Tuple[str, str]]:
    return EMERGENCY_CATEGORIES if kind == EMERGENCY else CIVIC_CATEGORIES


def category_label(kind: str, key: str) -> str:
    for code, label in categories_for(kind):
        if code == key:
            return label
    return ""
