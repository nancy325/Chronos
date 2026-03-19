"""
planner_agent.py - LLM-based planning with strict output constraints.

ROLE OF THE LLM:
- Takes validated location + weather context
- Generates 2 plan options: Original vs Weather-Optimized
- Outputs ONLY structured JSON (enforced via Pydantic)
- Cannot hallucinate impossible activities (already validated by pipeline)
- Cannot make up weather data (already fetched and provided)

The LLM is CONSTRAINED to:
1. Respect the validated location (can't suggest impossible activities)
2. Use ONLY provided weather data (no making up metrics)
3. Output only valid TaskStep objects (no free-form text)
4. Provide human-readable advice (not raw numbers)
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator
from enum import Enum


# ──────────────────────────────────────────────────────────────────────────────
# Output Contracts (Pydantic) — Enforce valid LLM output
# ──────────────────────────────────────────────────────────────────────────────

class TaskStep(BaseModel):
    """A single step in a plan — structured and validated."""
    
    order: int = Field(ge=1, description="Step number (1-indexed)")
    description: str = Field(min_length=10, max_length=500, description="What to do")
    time_from: Optional[str] = Field(
        default=None,
        pattern=r"^\d{2}:\d{2}$",
        description="Start time in HH:MM format"
    )
    time_to: Optional[str] = Field(
        default=None,
        pattern=r"^\d{2}:\d{2}$",
        description="End time in HH:MM format"
    )
    location: Optional[str] = Field(default=None, description="Where this happens")
    weather_sensitive: bool = Field(default=False, description="Is this affected by weather?")
    risk_note: Optional[str] = Field(default=None, description="Weather-related warnings")

    @field_validator("order")
    @classmethod
    def validate_order(cls, v, info):
        """Ensure step order is reasonable."""
        if v > 50:  # Sanity check: no plan should have 50+ steps
            raise ValueError("Plan cannot have more than 50 steps")
        return v


class PlanOption(BaseModel):
    """A complete plan option — enforced structure."""
    
    name: str = Field(max_length=50, description="Plan name (e.g., 'Original', 'Weather-Optimized')")
    summary: str = Field(min_length=20, max_length=200, description="One or two sentence summary")
    steps: list[TaskStep] = Field(min_items=1, max_items=50, description="Ordered steps")
    reasoning: str = Field(
        min_length=50,
        max_length=500,
        description="Why this plan is good given weather"
    )

    @field_validator("steps")
    @classmethod
    def validate_steps_ordered(cls, v):
        """Ensure steps are in correct order."""
        for i, step in enumerate(v, 1):
            if step.order != i:
                raise ValueError(f"Steps must be ordered 1 to {len(v)}")
        return v


class RiskLevel(str, Enum):
    """Risk assessment."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PlannedOutput(BaseModel):
    """Final output from the planning agent — strictly structured."""
    
    activity: str = Field(description="The planned activity")
    location: str = Field(description="Location for the activity")
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="Date in YYYY-MM-DD")
    
    # Feasibility assertion from LLM
    feasible: bool = Field(description="Can this activity happen here?")
    feasibility_note: str = Field(
        min_length=10,
        max_length=300,
        description="Why it's feasible or not"
    )
    
    # Plans
    plan_a: PlanOption = Field(description="Original plan as proposed by user")
    plan_b: Optional[PlanOption] = Field(
        default=None,
        description="Weather-optimized alternative (can be null if not applicable)"
    )
    
    # Overall risk
    overall_risk: RiskLevel = Field(description="Overall weather risk level")
    weather_note: str = Field(
        min_length=20,
        max_length=300,
        description="Summary of weather impact and recommendations"
    )


# ──────────────────────────────────────────────────────────────────────────────
# LLM PLANNING PROMPT TEMPLATE
# This is the EXACT prompt sent to the LLM
# ──────────────────────────────────────────────────────────────────────────────

FINAL_PLANNER_PROMPT_TEMPLATE = """You are Chronos, a weather-adaptive planning assistant.

Your job is to generate TWO plan options for the user's activity:
1. PLAN A: Original plan as requested
2. PLAN B: Weather-optimized alternative (if weather suggests a modification)

CRITICAL CONSTRAINTS:
- You can ONLY suggest activities that align with the location terrain
- You must use the provided weather data — do NOT make up temperatures or conditions
- You must output ONLY valid JSON matching the required schema
- Provide human-friendly advice about clothing/comfort, NOT raw metrics
- If weather is unavailable, do NOT hallucinate data — note it in your plan

LOCATION DETAILS:
- Name: {location_name}
- Terrain: {terrain_type}
- Country: {country}
- Latitude/Longitude: {latitude}, {longitude}

REQUESTED ACTIVITY: {activity}

FORECAST DATE: {forecast_date}

WEATHER DATA:
{weather_data}

YOUR TASK:

1. Confirm that "{activity}" is feasible at {location_name}
   (It passed our automated checks, but confirm your reasoning)

2. Create PLAN A (original as requested):
   - Title: Something like "Original Beach Day Plan"
   - 4-6 time-bounded steps
   - Each step should have: description, time range, location, weather-sensitivity flag

3. Create PLAN B (weather-optimized alternative):
   - If weather is bad, suggest a different time or activity variant
   - If weather is good, you can keep PLAN B = null or suggest an enhanced version
   - Example: If it's too hot, suggest an indoor alternative + evening beach trip

4. Assess overall risk (low/medium/high) based on weather

5. Provide weather advice:
   - Focus on HOW THE USER WILL FEEL
   - Suggest clothing adjustments
   - Mention comfort/safety considerations
   - Do NOT output raw weather metrics ("15°C, 60% humidity")
   - DO output: "You'll want a light jacket with a breeze"

IMPORTANT WEATHER GUIDELINES:
- If temp < 10°C: "You'll need warm layers"
- If temp 10-20°C: "A light jacket is good"
- If temp 20-25°C: "Perfect t-shirt weather"
- If temp > 30°C: "Hot—stay hydrated, wear light clothes"
- If rainy: "Bring an umbrella, plan indoor backup"
- If windy: "It'll be breezy—tie hair back if needed"

RESPOND WITH ONLY a valid JSON object (no markdown, no explanation):
{{
  "activity": "{activity}",
  "location": "{location_name}",
  "date": "{forecast_date}",
  "feasible": true or false,
  "feasibility_note": "Why this activity is feasible here...",
  "plan_a": {{
    "name": "Original Beach Day",
    "summary": "Traditional beach day with relaxation and swimming",
    "steps": [
      {{
        "order": 1,
        "description": "Pack sunscreen, swimsuit, and water bottle",
        "time_from": "08:00",
        "time_to": "08:30",
        "location": "Home",
        "weather_sensitive": false,
        "risk_note": null
      }},
      ...more steps...
    ],
    "reasoning": "This plan works well given the weather because..."
  }},
  "plan_b": {{
    "name": "Alternative: Evening Beach + Lunch",
    "summary": "Skip the heat, enjoy cooler evening hours",
    ...
  }},
  "overall_risk": "low" or "medium" or "high",
  "weather_note": "It'll be warm and sunny, so bring sunscreen and stay hydrated..."
}}

Generate the plan NOW:"""


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
    Generate the final planning prompt for the LLM.
    
    This is the exact prompt template with all values filled in.
    
    Args:
        activity: User's activity
        location_name: Full location name
        terrain_type: Terrain classification
        country: Country name
        latitude: Location latitude
        longitude: Location longitude
        forecast_date: Date for planning
        weather_data: Dict with temperature, condition, etc. (or None if unavailable)
        
    Returns:
        Complete prompt string for LLM
    """
    
    # Format weather data section
    if weather_data:
        weather_section = f"""
Temperature: {weather_data['temperature_celsius']}°C
Condition: {weather_data['condition']}
Precipitation Chance: {weather_data['precipitation_chance']}%
Wind Speed: {weather_data['wind_speed_kmh']} km/h
Humidity: {weather_data['humidity_percent']}%
UV Index: {weather_data['uv_index']}

Human-Friendly Summary: {weather_data['human_summary']}
"""
    else:
        weather_section = """
[Weather data unavailable for this date]
Note: Plan based on typical weather patterns, but you CANNOT make up specific weather metrics.
"""
    
    return FINAL_PLANNER_PROMPT_TEMPLATE.format(
        activity=activity,
        location_name=location_name,
        terrain_type=terrain_type,
        country=country,
        latitude=latitude,
        longitude=longitude,
        forecast_date=forecast_date,
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
        date="2026-03-16",
        feasible=True,
        feasibility_note="Goa is a coastal state with excellent beaches perfect for this activity.",
        plan_a=PlanOption(
            name="Classic Beach Day",
            summary="Sunrise swimming, beach relaxation, sunset dinner",
            steps=[
                TaskStep(
                    order=1,
                    description="Grab breakfast and pack sunscreen, hat, and swimsuit",
                    time_from="07:00",
                    time_to="07:30",
                    location="Hotel",
                    weather_sensitive=False,
                ),
                TaskStep(
                    order=2,
                    description="Head to Calangute Beach for morning swimming",
                    time_from="08:00",
                    time_to="10:30",
                    location="Calangute Beach, Goa",
                    weather_sensitive=True,
                    risk_note="Wear sunscreen—UV index will be high",
                ),
                TaskStep(
                    order=3,
                    description="Beach lunch at a beachside cafe",
                    time_from="12:30",
                    time_to="13:30",
                    location="Beachside Cafe",
                    weather_sensitive=False,
                ),
                TaskStep(
                    order=4,
                    description="Rest and relax on the beach",
                    time_from="14:00",
                    time_to="16:30",
                    location="Beach",
                    weather_sensitive=False,
                    risk_note="Stay in shade periodically to avoid heat exhaustion",
                ),
                TaskStep(
                    order=5,
                    description="Sunset dinner at beachfront restaurant",
                    time_from="18:00",
                    time_to="20:00",
                    location="Beachfront Restaurant",
                    weather_sensitive=False,
                ),
            ],
            reasoning="This plan maximizes beach time while managing UV exposure through timing.",
        ),
        plan_b=None,  # Weather is perfect, no alternative needed
        overall_risk="LOW",
        weather_note="Sunny with high UV index. Bring sunscreen and a hat. The light breeze will keep you comfortable even in the heat.",
    )
