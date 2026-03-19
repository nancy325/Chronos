"""
sanity_check.py - Geographic feasibility validator.

GUARDS AGAINST HALLUCINATION #2: Infeasible plans.

This module validates whether a requested activity is physically possible
at the given location BEFORE the LLM sees it. 

Examples of catches:
- "Beach day" at an inland location (BLOCKED)
- "Skiing" in a low-altitude desert (BLOCKED)
- "Desert safari" in a rainforest (BLOCKED)
- "Hiking" in a coastal city (ALLOWED - feasible anywhere with hills)

Prompt template included for LLM-based feasibility checks if needed.
"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum

from geocoding import Location, get_location_metadata


class FeasibilityStatus(str, Enum):
    """Outcome of feasibility check."""
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    REQUIRES_LLAMA_CHECK = "requires_llm_check"  # Complex case, ask LLM


@dataclass
class FeasibilityResult:
    """Result of activity feasibility check."""
    status: FeasibilityStatus
    reason: str                          # Why (in)feasible
    suggestion: Optional[str] = None     # Alternative location/activity if infeasible


# ──────────────────────────────────────────────────────────────────────────────
# ACTIVITY ← → TERRAIN COMPATIBILITY MATRIX
# Hardcoded rules that catch obvious hallucinations
# ──────────────────────────────────────────────────────────────────────────────

ACTIVITY_TERRAIN_RULES = {
    # Beach activities REQUIRE coastal terrain
    "beach": {
        "requires": ["coastal"],
        "forbidden": ["desert", "mountain", "plain"],
    },
    "surfing": {
        "requires": ["coastal"],
        "forbidden": ["desert", "mountain", "plain", "urban"],
    },
    "swimming": {
        "requires": ["coastal"],
        "forbidden": ["desert"],
    },
    
    # Skiing REQUIRES mountains + cold
    "skiing": {
        "requires": ["mountain"],
        "forbidden": ["coastal", "desert", "plain"],
    },
    "snowboarding": {
        "requires": ["mountain"],
        "forbidden": ["coastal", "desert"],
    },
    
    # Desert activities REQUIRE desert terrain
    "desert safari": {
        "requires": ["desert"],
        "forbidden": ["coastal", "mountain"],
    },
    "dune bashing": {
        "requires": ["desert"],
        "forbidden": ["coastal", "mountain", "plain"],
    },
    
    # Mountain activities REQUIRE mountains
    "mountaineering": {
        "requires": ["mountain"],
        "forbidden": ["desert", "coastal"],
    },
    "rock climbing": {
        "requires": ["mountain"],
        "forbidden": ["desert"],
    },
    
    # Flexible activities (allowed almost anywhere)
    "hiking": {
        "requires": None,  # Can be done almost anywhere
        "forbidden": [],
    },
    "picnic": {
        "requires": None,
        "forbidden": [],
    },
    "shopping": {
        "requires": None,
        "forbidden": [],
    },
    "office work": {
        "requires": None,
        "forbidden": [],
    },
    "reading": {
        "requires": None,
        "forbidden": [],
    },
    "meditation": {
        "requires": None,
        "forbidden": [],
    },
}


def check_activity_feasibility(activity: str, location: Location) -> FeasibilityResult:
    """
    Check if an activity is feasible at a location using hardcoded rules.
    
    RETURNS: FeasibilityResult with status and reasoning.
    
    This is a GUARDRAIL that prevents obvious hallucinations like
    "beach day in Anand" before the LLM ever sees it.
    
    Args:
        activity: User's requested activity (e.g., "beach day")
        location: Geocoded location
        
    Returns:
        FeasibilityResult object
    """
    activity_lower = activity.lower().strip()
    metadata = get_location_metadata(location)
    
    # Check exact activity match
    matched_activity = None
    for rule_activity, rule_config in ACTIVITY_TERRAIN_RULES.items():
        if rule_activity in activity_lower:
            matched_activity = rule_activity
            break
    
    # If no rule match, ask LLM for complex reasoning
    if not matched_activity:
        return FeasibilityResult(
            status=FeasibilityStatus.REQUIRES_LLAMA_CHECK,
            reason=f"Activity '{activity}' not in hardcoded rules. Delegating to LLM for feasibility check."
        )
    
    # Check against feasibility rules
    rule = ACTIVITY_TERRAIN_RULES[matched_activity]
    terrain_type = metadata["terrain_type"]
    
    # Check forbidden terrains
    if rule["forbidden"]:
        for forbidden in rule["forbidden"]:
            if forbidden in terrain_type.lower():
                suggestion = _suggest_alternative_location(activity_lower, forbidden)
                return FeasibilityResult(
                    status=FeasibilityStatus.INFEASIBLE,
                    reason=f"'{activity}' is not feasible in {terrain_type} terrain. {location.name} is {terrain_type}.",
                    suggestion=suggestion
                )
    
    # Check required terrains
    if rule["requires"]:
        has_required_terrain = any(req in terrain_type.lower() for req in rule["requires"])
        if not has_required_terrain:
            suggestion = _suggest_alternative_location(activity_lower, terrain_type)
            required_str = " or ".join(rule["requires"])
            return FeasibilityResult(
                status=FeasibilityStatus.INFEASIBLE,
                reason=f"'{activity}' requires {required_str} terrain. {location.name} is {terrain_type}.",
                suggestion=suggestion
            )
    
    # Passed all checks
    return FeasibilityResult(
        status=FeasibilityStatus.FEASIBLE,
        reason=f"'{activity}' is feasible at {location.name} ({terrain_type})."
    )


def _suggest_alternative_location(activity: str, current_terrain: str) -> Optional[str]:
    """
    Suggest a nearby alternative location for an infeasible activity.
    
    In production, this would use distance calculations and a real location DB.
    """
    suggestions = {
        ("beach", "plain"): "Mumbai or Goa (nearby coastal cities)",
        ("beach", "desert"): "Coastal cities with similar climate",
        ("skiing", "plain"): "Swiss Alps or Colorado (mountain regions)",
        ("desert safari", "coastal"): "Jaipur or Las Vegas (desert regions)",
    }
    
    for (activity_key, terrain_key), suggestion in suggestions.items():
        if activity_key in activity and terrain_key in current_terrain.lower():
            return f"Try {suggestion} instead."
    
    return None


# ──────────────────────────────────────────────────────────────────────────────
# LLM-BASED SANITY CHECK PROMPT (for complex activities)
# ──────────────────────────────────────────────────────────────────────────────

SANITY_CHECK_PROMPT_TEMPLATE = """You are a geographic reasoning expert. Your job is to validate whether an activity is physically possible at a given location.

LOCATION:
- Name: {location_name}
- Terrain: {terrain_type}
- Coordinates: {latitude}, {longitude}
- Region: {country}, {state}

REQUESTED ACTIVITY: {activity}

STRICT RULES:
1. Beach activities (swimming, surfing, beach volleyball) require coastal access
2. Skiing/snowboarding requires mountains with winter conditions
3. Desert safaris require desert terrain
4. Mountaineering requires mountain terrain
5. Urban activities can happen anywhere with cities

RESPOND WITH ONLY A JSON OBJECT (no markdown, no extra text):
{{
  "feasible": true or false,
  "reason": "Short explanation of why it's feasible or not",
  "suggestion": "If infeasible, suggest an alternative location. If feasible, set to null."
}}

Remember:
- A location is feasible unless there's a clear geographic impediment
- Office work and shopping are feasible almost anywhere
- Hiking can happen in various terrains
- Be conservative: if there's doubt, mark as infeasible

RESPOND NOW:"""


def get_sanity_check_prompt(activity: str, location: Location) -> str:
    """
    Generate a sanity check prompt for the LLM.
    
    Used when hardcoded rules don't cover the case.
    """
    metadata = get_location_metadata(location)
    return SANITY_CHECK_PROMPT_TEMPLATE.format(
        location_name=location.name,
        terrain_type=metadata["terrain_type"],
        latitude=location.latitude,
        longitude=location.longitude,
        country=metadata["country"],
        state=metadata["state"],
        activity=activity,
    )
