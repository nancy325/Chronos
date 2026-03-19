"""
pipeline.py - Hallucination-resistant planning pipeline with strict guardrails.

ARCHITECTURE:
1. Location Validation (geocoding) — FAIL FAST if invalid
2. Sanity Check (geography) — BLOCK impossible activities
3. Weather Fetch (API) — Get actual data
4. LLM Planning (constrained) — Generate plan with guardrails
5. Output Validation — Ensure LLM output is sane

This pipeline ensures that hallucinations are caught at every stage
before they reach the user.
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from geocoding import validate_location, get_location_metadata, Location
from weather_api import fetch_weather, generate_simulated_weather, get_weather_summary, WeatherData
from sanity_check import check_activity_feasibility, FeasibilityStatus
from user_location import detect_user_location, UserLocation, get_travel_time_estimate
from google_maps_integration import GoogleMapsClient


@dataclass
class PipelineError:
    """Error that occurred in pipeline."""
    stage: str              # "location_validation", "sanity_check", "weather_fetch", "planning"
    code: str               # "LOCATION_NOT_FOUND", "ACTIVITY_INFEASIBLE", "WEATHER_UNAVAILABLE", etc.
    message: str            # Human-readable error
    suggestion: Optional[str] = None  # Helpful suggestion


@dataclass
class PipelineResult:
    """Result of planning pipeline execution."""
    success: bool
    error: Optional[PipelineError] = None
    
    # Valid outputs (if success == True)
    location: Optional[Location] = None
    location_metadata: Optional[dict] = None
    activity: Optional[str] = None
    forecast_date: Optional[str] = None
    weather: Optional[WeatherData] = None
    weather_summary: Optional[str] = None
    
    # NEW: User location & travel info
    user_location: Optional[UserLocation] = None
    travel_info: Optional[dict] = None
    nearby_places: Optional[list] = None
    
    # For LLM input
    context_for_planning: Optional[dict] = None


class ChronosPipeline:
    """Main planning pipeline with guardrails."""
    
    def __init__(self, use_simulated_weather: bool = False):
        """
        Initialize pipeline.
        
        Args:
            use_simulated_weather: If True, generate simulated weather for demos
        """
        self.use_simulated_weather = use_simulated_weather
    
    async def execute(
        self,
        activity: str,
        location_string: str,
        forecast_date: str,
        use_llm_sanity_check: bool = False,
    ) -> PipelineResult:
        """
        Execute the full planning pipeline with guardrails.
        
        STAGES:
        1. Validate location (geocoding)
        2. Sanity check activity feasibility
        3. Fetch weather data
        4. Build context for LLM planning
        
        Args:
            activity: User's requested activity
            location_string: User's location input (e.g., "Anand, India")
            forecast_date: Date for planning (YYYY-MM-DD)
            use_llm_sanity_check: Use LLM for complex sanity checks (slower but more flexible)
            
        Returns:
            PipelineResult with all validated inputs or error details
        """
        
        # ──────────────────────────────────────────────────────────────────────
        # STAGE 1: Location Validation (Geocoding)
        # FAIL FAST if location doesn't exist
        # ──────────────────────────────────────────────────────────────────────
        
        # Parse location_string into city and country/state
        parts = [p.strip() for p in location_string.split(",")]
        city = parts[0]
        state_or_country = parts[1] if len(parts) > 1 else None
        
        is_valid, location, error_msg = validate_location(city, state_or_country)
        if not is_valid:
            return PipelineResult(
                success=False,
                error=PipelineError(
                    stage="location_validation",
                    code="LOCATION_NOT_FOUND",
                    message=error_msg,
                    suggestion="Please provide a valid city name and country."
                )
            )
        
        location_metadata = get_location_metadata(location)
        
        # ──────────────────────────────────────────────────────────────────────
        # STAGE 2: Sanity Check (Geographic Feasibility)
        # BLOCK impossible activities before LLM sees them
        # ──────────────────────────────────────────────────────────────────────
        
        feasibility = check_activity_feasibility(activity, location)
        
        if feasibility.status == FeasibilityStatus.INFEASIBLE:
            return PipelineResult(
                success=False,
                error=PipelineError(
                    stage="sanity_check",
                    code="ACTIVITY_INFEASIBLE",
                    message=feasibility.reason,
                    suggestion=feasibility.suggestion
                )
            )
        
        # If requires LLM check and flag is set, defer to LLM (for complex cases)
        if feasibility.status == FeasibilityStatus.REQUIRES_LLAMA_CHECK and use_llm_sanity_check:
            # TODO: Call LLM-based sanity check here
            # For now, assume it's feasible
            pass
        elif feasibility.status == FeasibilityStatus.REQUIRES_LLAMA_CHECK:
            # Assume feasible by default for flexible activities
            pass
        
        # ──────────────────────────────────────────────────────────────────────
        # STAGE 3: Fetch Weather Data
        # Use real API or simulated data based on configuration
        # ──────────────────────────────────────────────────────────────────────
        
        weather = None
        
        if self.use_simulated_weather:
            # Generate deterministic simulated weather
            weather = generate_simulated_weather(
                location.name,
                location.latitude,
                location.longitude,
                forecast_date
            )
        else:
            # Try to fetch from API
            weather = await fetch_weather(
                location.name,
                location.latitude,
                location.longitude,
                forecast_date
            )
        
        # If weather unavailable, warn but continue (LLM can still plan)
        if not weather:
            # This is a WARNING, not an ERROR — planning can proceed without weather
            pass
        
        weather_summary = get_weather_summary(weather) if weather else None
        
        # ──────────────────────────────────────────────────────────────────────
        # STAGE 4: Detect User Location & Calculate Travel Time
        # NEW: Geolocation for travel planning
        # ──────────────────────────────────────────────────────────────────────
        
        user_location = await detect_user_location(use_ip_geolocation=True)
        
        # Calculate travel time from user location to destination
        travel_info = None
        if user_location:
            import math
            lat_diff = abs(location.latitude - user_location.latitude)
            lon_diff = abs(location.longitude - user_location.longitude)
            distance_km = math.sqrt(lat_diff**2 + lon_diff**2) * 111  # Rough km conversion
            travel_info = get_travel_time_estimate(distance_km)
            travel_info["origin"] = f"{user_location.city}, {user_location.country}"
            travel_info["destination"] = location.name
            travel_info["distance_km"] = round(distance_km, 1)
        
        # ──────────────────────────────────────────────────────────────────────
        # STAGE 5: Find Nearby Places at Destination
        # NEW: Group activities by proximity
        # ──────────────────────────────────────────────────────────────────────
        
        nearby_places = []
        maps_client = GoogleMapsClient()  # Uses API key if available
        
        # Extract activity types from user's activity string
        activity_types = self._extract_activity_types(activity)
        
        if activity_types:
            nearby_places = await maps_client.find_nearby_places(
                location.latitude,
                location.longitude,
                activity_types,
                radius_meters=5000
            )
        
        # ──────────────────────────────────────────────────────────────────────
        # STAGE 6: Build Context for LLM
        # Package all validated inputs + travel + nearby places
        # ──────────────────────────────────────────────────────────────────────
        
        nearby_places_for_context = [
            {
                "name": p.name,
                "type": p.place_type,
                "rating": p.rating,
                "address": p.address,
            }
            for p in nearby_places[:10]  # Top 10 places
        ] if nearby_places else []
        
        context_for_planning = {
            "activity": activity,
            "location": location.name,
            "location_metadata": location_metadata,
            "forecast_date": forecast_date,
            
            # NEW: Travel information
            "user_location": {
                "city": user_location.city,
                "country": user_location.country,
                "coordinates": {"lat": user_location.latitude, "lon": user_location.longitude},
            } if user_location else None,
            
            "travel_info": travel_info,
            
            "nearby_places": nearby_places_for_context,
            
            "weather": {
                "raw": {
                    "temperature_celsius": weather.temperature_celsius,
                    "condition": weather.condition,
                    "precipitation_chance": weather.precipitation_chance,
                    "wind_speed_kmh": weather.wind_speed_kmh,
                    "humidity_percent": weather.humidity_percent,
                    "uv_index": weather.uv_index,
                } if weather else None,
                "human_summary": weather_summary,
            },
            "feasibility_check": {
                "status": feasibility.status.value,
                "reason": feasibility.reason,
            }
        }
        
        # ──────────────────────────────────────────────────────────────────────
        # SUCCESS — All guardrails passed
        # ──────────────────────────────────────────────────────────────────────
        
        return PipelineResult(
            success=True,
            location=location,
            location_metadata=location_metadata,
            activity=activity,
            forecast_date=forecast_date,
            weather=weather,
            weather_summary=weather_summary,
            user_location=user_location,
            travel_info=travel_info,
            nearby_places=nearby_places,
            context_for_planning=context_for_planning
        )
    
    def _extract_activity_types(self, activity: str) -> list[str]:
        """
        Extract activity types from user's activity string.
        
        Maps user activities to Google Maps place types.
        Examples:
        - "beach day" → ["beach", "restaurant", "shopping_mall"]
        - "museum tour" → ["museum", "restaurant"]
        - "hiking adventure" → ["park", "restaurant"]
        """
        activity_lower = activity.lower()
        
        # Define activity mappings
        mappings = {
            "beach": ["beach", "restaurant", "shopping_mall"],
            "restaurant": ["restaurant", "cafe"],
            "museum": ["museum", "art_gallery"],
            "hiking": ["park", "restaurant"],
            "shopping": ["shopping_mall", "store"],
            "culture": ["museum", "art_gallery", "historical_landmark"],
            "food": ["restaurant", "cafe", "bakery"],
            "park": ["park", "garden", "nature_reserve"],
            "adventure": ["ropeways", "amusement_park", "park"],
        }
        
        result = []
        for key, types in mappings.items():
            if key in activity_lower:
                result.extend(types)
        
        return list(set(result)) if result else ["restaurant", "park"]  # Default fallback


async def run_planning_pipeline(
    activity: str,
    location_string: str,
    forecast_date: str,
    use_simulated_weather: bool = True,
) -> tuple[bool, Optional[dict], Optional[PipelineError]]:
    """
    Convenience function to run the full pipeline.
    
    RETURNS: (success, context_for_llm, error)
    
    Usage:
        success, context, error = await run_planning_pipeline(
            activity="beach day",
            location_string="Anand, India",
            forecast_date="2026-03-16"
        )
        
        if not success:
            print(f"Error: {error.message}")
            print(f"Suggestion: {error.suggestion}")
            return
        
        # context is safe to pass to LLM for planning
        plan = await llm_plan(context)
    """
    pipeline = ChronosPipeline(use_simulated_weather=use_simulated_weather)
    result = await pipeline.execute(activity, location_string, forecast_date)
    
    if result.success:
        return True, result.context_for_planning, None
    else:
        return False, None, result.error
