"""
pipeline.py - Chronos planning pipeline with dynamic workflow.

REVISED WORKFLOW (6 Stages):
  • Step 1: Parse User Prompt (Location, Activity, Duration)
  • Step 2: Feasibility Check (Geocoding + Activity Validation)
      → Fail fast if location invalid or activity infeasible
  • Step 3: Enrichment (non-blocking parallel):
      • Fetch Weather Data (informational, never blocks)
      • Detect User Location & Calculate Travel Time
  • Step 4: Duration Logic (parse requested duration—supports 1 day to weeks)
  • Step 5: Context Preparation (aggregate Weather + Travel + OSM Places)
  • Step 6: Hand-off PlannerContext to planner_agent.py for LLM generation

API INTEGRATION:
  • Location Validation: Geocoding via OpenStreetMap Nominatim
  • Place Suggestions: OpenStreetMap Overpass API (no rate limits, no key needed)
  • Weather Data: Configurable (simulated or external API)
  • User Geolocation: IP-based fallback
"""

from __future__ import annotations

import asyncio
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from geocoding import validate_location, get_location_metadata, Location
from weather_api import fetch_weather, generate_simulated_weather, get_weather_summary, WeatherData
from sanity_check import check_activity_feasibility, FeasibilityStatus
from user_location import detect_user_location, UserLocation, get_travel_time_estimate
from google_maps_integration import GoogleMapsClient, PlaceResult


# ──────────────────────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PipelineError:
    """Error that occurred in the pipeline."""
    stage: str              # "location_validation", "sanity_check", "weather_fetch", "planning"
    code: str               # "LOCATION_NOT_FOUND", "ACTIVITY_INFEASIBLE", etc.
    message: str
    suggestion: Optional[str] = None


@dataclass
class DurationInfo:
    """Dynamic duration details parsed from user input."""
    total_days: int = 1
    start_date: str = ""          # YYYY-MM-DD
    end_date: str = ""            # YYYY-MM-DD
    raw_input: Optional[str] = None
    defaulted: bool = False       # True if no duration was specified → used default


@dataclass
class PlannerContext:
    """
    Complete context object handed off to planner_agent.py.

    This dataclass represents the fully-validated, enriched planning context.
    The PlannedAgent receives this and generates 2 plan options without
    needing to re-validate or make external API calls.

    Fields:
      • activity, location_name, location_metadata: Validated destination
      • duration: Parsed trip duration (1 day → weeks, computed end date)
      • weather: Actual weather data (never hallucinated by LLM)
      • user_location, travel_info: Origin location + travel time estimate
      • nearby_places: POIs from OpenStreetMap Overpass API
      • feasibility: Terrain validation results
    """
    activity: str
    location_name: str
    location_metadata: dict
    duration: DurationInfo
    weather: Optional[dict] = None            # raw weather fields
    weather_summary: Optional[str] = None     # human-friendly summary
    user_location: Optional[dict] = None      # origin city/country/coords
    travel_info: Optional[dict] = None        # mode, minutes, description
    nearby_places: list[dict] = field(default_factory=list)
    feasibility: Optional[dict] = None


@dataclass
class PipelineResult:
    """Result of planning pipeline execution."""
    success: bool
    error: Optional[PipelineError] = None

    # Validated intermediate data
    location: Optional[Location] = None
    location_metadata: Optional[dict] = None
    activity: Optional[str] = None
    duration: Optional[DurationInfo] = None
    weather: Optional[WeatherData] = None
    weather_summary: Optional[str] = None

    # Enrichment data
    user_location: Optional[UserLocation] = None
    travel_info: Optional[dict] = None
    nearby_places: Optional[list] = None

    # Hand-off payload for planner_agent
    context_for_planner: Optional[PlannerContext] = None


# ──────────────────────────────────────────────────────────────────────────────
# Duration Helpers
# ──────────────────────────────────────────────────────────────────────────────

_DURATION_PATTERN = re.compile(
    r"(\d+)\s*(day|days|week|weeks|night|nights)", re.IGNORECASE
)

DEFAULT_DURATION_DAYS = 3  # sensible default when user omits duration


def parse_duration(user_input: str, forecast_date: str) -> DurationInfo:
    """
    Extract the number of requested days from the user's prompt.

    Supports dynamic patterns:
      • Single units: "5 days", "1 week", "2 weeks", "15 days", "3 nights"
      • Fallback: DEFAULT_DURATION_DAYS (3) if no duration specified
      • Range calculation: Computes end_date automatically

    Returns:
      DurationInfo with total_days, start/end dates, and defaulted flag.
    """
    match = _DURATION_PATTERN.search(user_input)
    if match:
        value = int(match.group(1))
        unit = match.group(2).lower()
        if "week" in unit:
            total_days = value * 7
        else:
            total_days = max(value, 1)
        defaulted = False
    else:
        total_days = DEFAULT_DURATION_DAYS
        defaulted = True

    start = datetime.strptime(forecast_date, "%Y-%m-%d")
    end = start + timedelta(days=max(total_days - 1, 0))

    return DurationInfo(
        total_days=total_days,
        start_date=forecast_date,
        end_date=end.strftime("%Y-%m-%d"),
        raw_input=user_input,
        defaulted=defaulted,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Activity → OpenStreetMap Place-Type Mapping
# ──────────────────────────────────────────────────────────────────────────────

_ACTIVITY_TYPE_MAP: dict[str, list[str]] = {
    "beach":      ["beach", "restaurant", "shopping_mall"],
    "restaurant": ["restaurant", "cafe"],
    "museum":     ["museum", "art_gallery"],
    "hiking":     ["park", "restaurant"],
    "shopping":   ["shopping_mall", "store"],
    "culture":    ["museum", "art_gallery", "historical_landmark"],
    "food":       ["restaurant", "cafe", "bakery"],
    "park":       ["park", "garden", "nature_reserve"],
    "adventure":  ["ropeways", "amusement_park", "park"],
}


def _extract_activity_types(activity: str) -> list[str]:
    """Map user activity keywords to OpenStreetMap Overpass place types."""
    lower = activity.lower()
    result: list[str] = []
    for key, types in _ACTIVITY_TYPE_MAP.items():
        if key in lower:
            result.extend(types)
    return list(set(result)) if result else ["restaurant", "park"]


# ──────────────────────────────────────────────────────────────────────────────
# Main Pipeline
# ──────────────────────────────────────────────────────────────────────────────

class ChronosPipeline:
    """Chronos planning pipeline with guardrails and enrichment stages."""

    def __init__(self, use_simulated_weather: bool = False):
        self.use_simulated_weather = use_simulated_weather

    async def execute(
        self,
        activity: str,
        location_string: str,
        forecast_date: str,
        duration_hint: str = "",
        use_llm_sanity_check: bool = False,
    ) -> PipelineResult:
        """
        Execute the full 6-stage pipeline.

        Stages:
          • Step 1: Parse prompt (location/activity/duration)
          • Step 2: Feasibility check (geocoding + terrain validation)
          • Step 3: Enrichment (weather + user location + travel time)
              ↳ Non-blocking: all tasks run concurrently
          • Step 4: Duration parsing (supports "1 week", "15 days", etc.)
          • Step 5: Context aggregation (all data → PlannerContext)
          • Step 6: Hand-off context to planner_agent.py

        Returns:
          PipelineResult with success flag, context_for_planner (if successful),
          or detailed error information (if failed).
        """

        # ── STEP 1: Parse user prompt ────────────────────────────────────
        parts = [p.strip() for p in location_string.split(",")]
        city = parts[0]
        state_or_country = parts[1] if len(parts) > 1 else None

        # ── STEP 2: Feasibility check (geocoding + terrain) ──────────────
        is_valid, location, error_msg = validate_location(city, state_or_country)
        if not is_valid:
            return PipelineResult(
                success=False,
                error=PipelineError(
                    stage="location_validation",
                    code="LOCATION_NOT_FOUND",
                    message=error_msg,
                    suggestion="Please provide a valid city name and country.",
                ),
            )

        location_metadata = get_location_metadata(location)

        feasibility = check_activity_feasibility(activity, location)
        if feasibility.status == FeasibilityStatus.INFEASIBLE:
            return PipelineResult(
                success=False,
                error=PipelineError(
                    stage="sanity_check",
                    code="ACTIVITY_INFEASIBLE",
                    message=feasibility.reason,
                    suggestion=feasibility.suggestion,
                ),
            )

        # If requires LLM check — let it pass (planner will do deeper check)
        if feasibility.status == FeasibilityStatus.REQUIRES_LLAMA_CHECK and use_llm_sanity_check:
            pass  # deferred to planner_agent

        # ── STEP 3: Enrichment (non-blocking parallel tasks) ─────────────
        #   • Weather fetch (informational — never blocks pipeline)
        #   • User location detection + travel time calculation
        #   • Nearby places discovery (OpenStreetMap Overpass API)

        weather_task = asyncio.create_task(
            self._fetch_weather_safe(location, forecast_date)
        )
        user_loc_task = asyncio.create_task(
            detect_user_location(use_ip_geolocation=True)
        )
        places_task = asyncio.create_task(
            self._fetch_nearby_places(location, activity)
        )

        # Await all enrichment concurrently
        weather, user_location, nearby_places = await asyncio.gather(
            weather_task, user_loc_task, places_task
        )

        weather_summary = get_weather_summary(weather) if weather else None

        # Travel time from user to destination
        travel_info = None
        if user_location:
            lat_diff = abs(location.latitude - user_location.latitude)
            lon_diff = abs(location.longitude - user_location.longitude)
            distance_km = math.sqrt(lat_diff ** 2 + lon_diff ** 2) * 111
            travel_info = get_travel_time_estimate(distance_km)
            travel_info["origin"] = f"{user_location.city}, {user_location.country}"
            travel_info["destination"] = location.name
            travel_info["distance_km"] = round(distance_km, 1)

        # ── STEP 4: Duration logic ───────────────────────────────────────
        raw_duration_text = duration_hint or activity
        duration = parse_duration(raw_duration_text, forecast_date)

        # ── STEP 5: Context preparation ──────────────────────────────────
        nearby_for_ctx = [
            {
                "name": p.name,
                "type": p.place_type,
                "rating": p.rating,
                "address": p.address,
            }
            for p in (nearby_places or [])[:10]
        ]

        planner_context = PlannerContext(
            activity=activity,
            location_name=location.name,
            location_metadata=location_metadata,
            duration=duration,
            weather={
                "temperature_celsius": weather.temperature_celsius,
                "condition": weather.condition,
                "precipitation_chance": weather.precipitation_chance,
                "wind_speed_kmh": weather.wind_speed_kmh,
                "humidity_percent": weather.humidity_percent,
                "uv_index": weather.uv_index,
            } if weather else None,
            weather_summary=weather_summary,
            user_location={
                "city": user_location.city,
                "country": user_location.country,
                "coordinates": {"lat": user_location.latitude, "lon": user_location.longitude},
            } if user_location else None,
            travel_info=travel_info,
            nearby_places=nearby_for_ctx,
            feasibility={
                "status": feasibility.status.value,
                "reason": feasibility.reason,
            },
        )

        # ── STEP 6: Hand off to planner_agent ────────────────────────────
        #  Pipeline validation & enrichment COMPLETE.
        #  Control passes to planner_agent.py for LLM-based plan generation.
        #  The planner has everything it needs; no additional API calls required.

        return PipelineResult(
            success=True,
            location=location,
            location_metadata=location_metadata,
            activity=activity,
            duration=duration,
            weather=weather,
            weather_summary=weather_summary,
            user_location=user_location,
            travel_info=travel_info,
            nearby_places=nearby_places,
            context_for_planner=planner_context,
        )

    # ── Private helpers ───────────────────────────────────────────────────

    async def _fetch_weather_safe(
        self, location: Location, forecast_date: str
    ) -> Optional[WeatherData]:
        """Fetch weather; returns None on failure (non-blocking)."""
        try:
            if self.use_simulated_weather:
                return generate_simulated_weather(
                    location.name, location.latitude, location.longitude, forecast_date
                )
            # fetch_weather is synchronous — run in a thread to avoid blocking
            return await asyncio.to_thread(
                fetch_weather,
                location.name, location.latitude, location.longitude, forecast_date,
            )
        except Exception:
            return None  # weather is informational; never blocks

    async def _fetch_nearby_places(
        self, location: Location, activity: str
    ) -> list[PlaceResult]:
        """Find nearby places via OpenStreetMap Overpass API (free, no limits)."""
        maps_client = GoogleMapsClient()  # Backed by OSM APIs
        place_types = _extract_activity_types(activity)
        try:
            return await maps_client.find_nearby_places(
                location.latitude, location.longitude, place_types, radius_meters=5000
            )
        except Exception:
            return []


# ──────────────────────────────────────────────────────────────────────────────
# Convenience wrapper
# ──────────────────────────────────────────────────────────────────────────────

async def run_planning_pipeline(
    activity: str,
    location_string: str,
    forecast_date: str,
    duration_hint: str = "",
    use_simulated_weather: bool = True,
) -> tuple[bool, Optional[PlannerContext], Optional[PipelineError]]:
    """
    Run the full pipeline and return (success, planner_context, error).

    Dynamic Duration Handling:
      • If duration_hint contains "3 weeks"/"5 days"/etc., uses that
      • Otherwise, searches user's activity/message for duration patterns
      • Falls back to DEFAULT_DURATION_DAYS (3 days) if no match found

    Usage:
        success, ctx, error = await run_planning_pipeline(
            activity="beach day for 1 week",
            location_string="Goa, India",
            forecast_date="2026-03-16",
        )
        # Duration auto-detected as 7 days

        if not success:
            print(f"Error: {error.message}")
            return

        # ctx is a fully-validated PlannerContext ready for planner_agent
        from planner_agent import generate_plan
        plan = await generate_plan(ctx)
    """
    pipeline = ChronosPipeline(use_simulated_weather=use_simulated_weather)
    result = await pipeline.execute(
        activity, location_string, forecast_date, duration_hint=duration_hint
    )

    if result.success:
        return True, result.context_for_planner, None
    return False, None, result.error
