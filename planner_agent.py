"""
planner_agent.py - LLM-based planning with strict output constraints.

ROLE:
  • Receives a fully-validated PlannerContext from pipeline.py
  • Generates 1 optimized plan using real tourist places
  • Outputs ONLY structured JSON (enforced via Pydantic)
  • Cannot hallucinate impossible activities (already validated by pipeline)
  • Cannot make up weather data (already fetched and provided)

CONSTRAINTS:
  1. Respect the validated location (can't suggest impossible activities)
  2. Use ONLY provided weather data (no making up metrics)
  3. Output only valid TaskStep objects (no free-form text)
  4. Provide human-readable advice (not raw numbers)
  5. Support flexible durations (1 day → weeks)
  6. Use nearby_places (OSM POIs) for real location names
  7. For multi-day: include packing_list with essentials for entire trip
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from pydantic import BaseModel, Field, field_validator
from enum import Enum

if TYPE_CHECKING:
    from pipeline import PlannerContext


# ──────────────────────────────────────────────────────────────────────────────
# Output Contracts (Pydantic) — Enforce valid LLM output
# ──────────────────────────────────────────────────────────────────────────────

class TaskStep(BaseModel):
    """A single step in a plan — structured and validated."""

    order: int = Field(ge=1, description="Step number (1-indexed)")
    description: str = Field(min_length=10, max_length=500, description="What to do")
    day: Optional[int] = Field(
        default=None,
        description="Which day of the trip this step belongs to (1-indexed)",
    )
    time_from: Optional[str] = Field(
        default=None,
        pattern=r"^\d{2}:\d{2}$",
        description="Start time in HH:MM format",
    )
    time_to: Optional[str] = Field(
        default=None,
        pattern=r"^\d{2}:\d{2}$",
        description="End time in HH:MM format",
    )
    location: Optional[str] = Field(default=None, description="Where this happens")
    weather_sensitive: bool = Field(default=False, description="Is this affected by weather?")
    risk_note: Optional[str] = Field(default=None, description="Weather-related warnings")

    @field_validator("order")
    @classmethod
    def validate_order(cls, v, info):
        if v > 50:
            raise ValueError("Plan cannot have more than 50 steps")
        return v


class PlanOption(BaseModel):
    """A complete plan option — enforced structure."""

    name: str = Field(max_length=50, description="Plan name")
    summary: str = Field(min_length=20, max_length=200, description="One or two sentence summary")
    steps: list[TaskStep] = Field(min_length=1, max_length=50, description="Ordered steps")
    reasoning: str = Field(
        min_length=50,
        max_length=500,
        description="Why this plan is good given weather",
    )
    packing_list: Optional[list[str]] = Field(
        default=None,
        description="Items to pack for the trip (only for multi-day plans)"
    )

    @field_validator("steps")
    @classmethod
    def validate_steps_ordered(cls, v):
        for i, step in enumerate(v, 1):
            if step.order != i:
                raise ValueError(f"Steps must be ordered 1 to {len(v)}")
        return v


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PlannedOutput(BaseModel):
    """Final output from the planning agent — strictly structured."""

    activity: str = Field(description="The planned activity")
    location: str = Field(description="Location for the activity")
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="Start date YYYY-MM-DD")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="End date YYYY-MM-DD")
    total_days: int = Field(ge=1, description="Total number of days in the plan")

    # Feasibility assertion from LLM
    feasible: bool = Field(description="Can this activity happen here?")
    feasibility_note: str = Field(
        min_length=10,
        max_length=300,
        description="Why it's feasible or not",
    )

    # Plans
    plan_a: PlanOption = Field(description="Optimized plan for the activity")

    # Overall risk
    overall_risk: RiskLevel = Field(description="Overall weather risk level")
    weather_note: str = Field(
        min_length=20,
        max_length=300,
        description="Summary of weather impact and recommendations",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Prompt Template (supports flexible duration)
# ──────────────────────────────────────────────────────────────────────────────

FINAL_PLANNER_PROMPT_TEMPLATE = """You are Chronos, a weather-adaptive planning assistant.

Your job is to generate ONE optimized plan for the user's activity, using real tourist places from the provided nearby places list.

CRITICAL CONSTRAINTS:
- You can ONLY suggest activities that align with the location terrain
- You must use the provided weather data — do NOT make up temperatures or conditions
- You must output ONLY valid JSON matching the required schema
- Provide human-friendly advice about clothing/comfort, NOT raw metrics
- If weather is unavailable, do NOT hallucinate data — note it in your plan
- Use real place names from the NEARBY PLACES list (e.g., actual restaurants, museums, temples)
- For multi-day trips (>1 day): include a packing_list of essentials for the entire trip

LOCATION DETAILS:
- Name: {location_name}
- Terrain: {terrain_type}
- Country: {country}
- Latitude/Longitude: {latitude}, {longitude}

REQUESTED ACTIVITY: {activity}

DURATION: {total_days} day(s)  ({start_date} → {end_date})

{travel_section}

{nearby_section}

IMPORTANT: Use place names from the NEARBY PLACES list above when creating activities.
Don't say "beach" — say the actual beach name. Don't say "restaurant" — use actual place names from the list.

WEATHER DATA:
{weather_data}

YOUR TASK:

1. Confirm that "{activity}" is feasible at {location_name}
   (It passed our automated checks, but confirm your reasoning)

2. Create PLAN A (optimized plan):
   - Title: Something like "Perfect Beach Day at Goa"
   - For single-day plans: 4-6 time-bounded steps with specific real place names from the nearby places list
   - For multi-day plans:
     • 3-5 steps PER DAY, each with "day" field (day: 1, 2, 3...)
     • Include packing_list array with 5-8 essential items for the full trip trip
     • Example packing_list: ["Light summer clothes", "Sunscreen SPF 50+", "Hat", "Comfortable walking shoes", "Refillable water bottle"]
   - Each step location field MUST use real place names from NEARBY PLACES list, not generic names
   - Each step should have: description, day (if multi-day), time range, location, weather-sensitivity flag

3. Assess overall risk (low/medium/high) based on weather

4. Provide weather advice:
   - Focus on HOW THE USER WILL FEEL
   - Suggest clothing adjustments
   - Do NOT output raw weather metrics
   - DO output: "You'll want a light jacket with a breeze"

RESPOND WITH ONLY a valid JSON object (no markdown, no explanation):
{
  "activity": "{activity}",
  "location": "{location_name}",
  "start_date": "{start_date}",
  "end_date": "{end_date}",
  "total_days": {total_days},
  "feasible": true or false,
  "feasibility_note": "Why this activity is feasible here...",
  "plan_a": {
    "name": "Your Adventure",
    "summary": "...",
    "steps": [
      {
        "order": 1,
        "day": 1,
        "description": "Visit [REAL PLACE NAME from nearby places list]",
        "time_from": "08:00",
        "time_to": "08:30",
        "location": "[REAL PLACE from list]",
        "weather_sensitive": false,
        "risk_note": null
      }
    ],
    "packing_list": ["item1", "item2"] (for multi-day) or null (for single-day),
    "reasoning": "..."
  },
  "overall_risk": "low" or "medium" or "high",
  "weather_note": "..."
}

Generate the plan NOW:"""


# ──────────────────────────────────────────────────────────────────────────────
# Prompt Builder — consumes PlannerContext from pipeline
# ──────────────────────────────────────────────────────────────────────────────

def build_planner_prompt(ctx) -> str:
    """
    Build the final LLM prompt from a PlannerContext object.

    Args:
        ctx: PlannerContext produced by pipeline.execute()

    Returns:
        Fully-interpolated prompt string ready for the LLM.
    """
    meta = ctx.location_metadata or {}
    duration = ctx.duration

    # ── Weather section ───────────────────────────────────────────────────
    if ctx.weather:
        weather_section = (
            f"Temperature: {ctx.weather['temperature_celsius']}°C\n"
            f"Condition: {ctx.weather['condition']}\n"
            f"Precipitation Chance: {ctx.weather['precipitation_chance']}%\n"
            f"Wind Speed: {ctx.weather['wind_speed_kmh']} km/h\n"
            f"Humidity: {ctx.weather['humidity_percent']}%\n"
            f"UV Index: {ctx.weather.get('uv_index', 'N/A')}\n"
        )
        if ctx.weather_summary:
            weather_section += f"\nHuman-Friendly Summary: {ctx.weather_summary}\n"
    else:
        weather_section = (
            "[Weather data unavailable for this date]\n"
            "Note: Plan based on typical weather patterns, but do NOT make up specific metrics.\n"
        )

    # ── Travel section ────────────────────────────────────────────────────
    if ctx.travel_info:
        travel_section = (
            "TRAVEL INFORMATION:\n"
            f"- From: {ctx.travel_info.get('origin', 'Unknown')}\n"
            f"- To: {ctx.travel_info.get('destination', ctx.location_name)}\n"
            f"- Distance: {ctx.travel_info.get('distance_km', '?')} km\n"
            f"- Estimated: {ctx.travel_info.get('description', 'Unknown')}\n"
        )
    else:
        travel_section = ""

    # ── Nearby places section ─────────────────────────────────────────────
    if ctx.nearby_places:
        lines = ["NEARBY PLACES (from OpenStreetMap):"]
        for p in ctx.nearby_places[:8]:
            lines.append(f"  - {p['name']} ({p['type']}) — {p.get('address', '')}")
        nearby_section = "\n".join(lines)
    else:
        nearby_section = ""

    return FINAL_PLANNER_PROMPT_TEMPLATE.format(
        activity=ctx.activity,
        location_name=ctx.location_name,
        terrain_type=meta.get("terrain_type", "unknown"),
        country=meta.get("country", "Unknown"),
        latitude=meta.get("latitude", 0),
        longitude=meta.get("longitude", 0),
        total_days=duration.total_days,
        start_date=duration.start_date,
        end_date=duration.end_date,
        travel_section=travel_section,
        nearby_section=nearby_section,
        weather_data=weather_section,
    )


# Legacy adapter — keeps backwards compatibility with old callers
def get_final_planner_prompt(
    activity: str,
    location_name: str,
    terrain_type: str,
    country: str,
    latitude: float,
    longitude: float,
    forecast_date: str,
    weather_data: Optional[dict],
) -> str:
    """
    Generate the planning prompt for the LLM (legacy interface).

    Prefer ``build_planner_prompt(ctx)`` for new code.
    """
    if weather_data:
        weather_section = (
            f"Temperature: {weather_data['temperature_celsius']}°C\n"
            f"Condition: {weather_data['condition']}\n"
            f"Precipitation Chance: {weather_data['precipitation_chance']}%\n"
            f"Wind Speed: {weather_data['wind_speed_kmh']} km/h\n"
            f"Humidity: {weather_data['humidity_percent']}%\n"
            f"UV Index: {weather_data.get('uv_index', 'N/A')}\n"
            f"\nHuman-Friendly Summary: {weather_data.get('human_summary', 'N/A')}\n"
        )
    else:
        weather_section = (
            "[Weather data unavailable for this date]\n"
            "Note: Plan based on typical weather patterns, but you CANNOT make up specific weather metrics.\n"
        )

    return FINAL_PLANNER_PROMPT_TEMPLATE.format(
        activity=activity,
        location_name=location_name,
        terrain_type=terrain_type,
        country=country,
        latitude=latitude,
        longitude=longitude,
        total_days=1,
        start_date=forecast_date,
        end_date=forecast_date,
        travel_section="",
        nearby_section="",
        weather_data=weather_section,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Example usage (for testing/documentation)
# ──────────────────────────────────────────────────────────────────────────────

def example_llm_output():
    """Example of valid LLM output matching our schema."""
    return PlannedOutput(
        activity="Beach day",
        location="Goa, India",
        start_date="2026-03-16",
        end_date="2026-03-16",
        total_days=1,
        feasible=True,
        feasibility_note="Goa is a coastal state with excellent beaches perfect for this activity.",
        plan_a=PlanOption(
            name="Classic Beach Day",
            summary="Sunrise swimming, beach relaxation, sunset dinner",
            steps=[
                TaskStep(
                    order=1,
                    day=1,
                    description="Grab breakfast and pack sunscreen, hat, and swimsuit",
                    time_from="07:00",
                    time_to="07:30",
                    location="Hotel",
                    weather_sensitive=False,
                ),
                TaskStep(
                    order=2,
                    day=1,
                    description="Head to Calangute Beach for morning swimming",
                    time_from="08:00",
                    time_to="10:30",
                    location="Calangute Beach, Goa",
                    weather_sensitive=True,
                    risk_note="Wear sunscreen—UV index will be high",
                ),
                TaskStep(
                    order=3,
                    day=1,
                    description="Beach lunch at a beachside cafe",
                    time_from="12:30",
                    time_to="13:30",
                    location="Beachside Cafe",
                    weather_sensitive=False,
                ),
                TaskStep(
                    order=4,
                    day=1,
                    description="Rest and relax on the beach",
                    time_from="14:00",
                    time_to="16:30",
                    location="Beach",
                    weather_sensitive=False,
                    risk_note="Stay in shade periodically to avoid heat exhaustion",
                ),
                TaskStep(
                    order=5,
                    day=1,
                    description="Sunset dinner at beachfront restaurant",
                    time_from="18:00",
                    time_to="20:00",
                    location="Beachfront Restaurant",
                    weather_sensitive=False,
                ),
            ],
            reasoning="This plan maximizes beach time while managing UV exposure through timing.",
        ),
        plan_b=None,
        overall_risk="low",
        weather_note="Sunny with high UV index. Bring sunscreen and a hat. The light breeze will keep you comfortable even in the heat.",
    )
