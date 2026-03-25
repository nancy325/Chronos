# Chronos – Technical Architecture Guide

## Overview

Chronos is a 6-stage planning pipeline that combines real-time validation, weather enrichment, and LLM-powered optimization to generate weather-adaptive travel plans.

---

## 6-Stage Pipeline Architecture

### Stage 1: Parse User Prompt
- Extract location, activity, and duration from user input
- Prepare data for validation stages

### Stage 2: Feasibility Check
**Geocoding** (`geocoding.py`):
- Validates location exists using OpenStreetMap Nominatim
- Returns coordinates, terrain type, and metadata
- **Fail-fast**: Returns error immediately if location invalid

**Activity Feasibility** (`sanity_check.py`):
- Checks if activity is geographically viable (e.g., beach requires coastal)
- **Fail-fast**: Blocks impossible activities before LLM sees them
- Returns `FEASIBLE`, `INFEASIBLE`, or `REQUIRES_LLM_CHECK`

### Stage 3: Enrichment (Non-blocking Parallel)

Three concurrent async tasks:

1. **Weather Fetch** (`weather_api.py`):
   - Fetches real weather data from wttr.in or simulates for offline demos
   - Never blocks pipeline (informational only)
   - Returns weather summary + human-friendly advice

2. **User Location Detection** (`user_location.py`):
   - IP-based geolocation to find user's current location
   - Calculates travel time estimate (user location → destination)
   - Non-blocking fallback if failed

3. **POI Discovery** (`google_maps_integration.py`):
   - Finds nearby places using OpenStreetMap Overpass API
   - Returns actual tourist attractions, restaurants, temples (not generic names)
   - Non-blocking: Returns empty list if failed

### Stage 4: Duration Logic
**Duration Parsing** (`pipeline.py`):
- Regex pattern matching: `(\d+)\s*(day|days|week|weeks|night|nights)`
- Supports: "5 days", "1 week", "2 weeks", "15 days", "3 nights"
- Fallback: 3 days if no duration detected
- Computes end date automatically

### Stage 5: Context Preparation
Aggregates all validated + enriched data into `PlannerContext`:
```python
@dataclass
class PlannerContext:
    activity: str
    location_name: str
    location_metadata: dict
    duration: DurationInfo(total_days, start_date, end_date)
    weather: dict | None
    weather_summary: str | None
    user_location: dict | None
    travel_info: dict | None
    nearby_places: list[dict]  # Real OSM POIs
    feasibility: dict
```

### Stage 6: Hand-off to planner_agent.py
- Pipeline passes `PlannerContext` to LLM planner
- LLM receives all validated data + nearby places
- **No additional API calls needed**
- LLM generates 1 optimized plan with:
  - Real place names (from OSM list)
  - Time-bounded steps (day-by-day for multi-day)
  - Packing list (for multi-day trips)
  - Risk assessment

---

## Core Modules

### app.py – Streamlit UI
- **Responsibility**: User interface, session state management
- **Key Features**:
  - Location auto-detect via IP-based geolocation
  - Multi-day date range picker
  - Displays plans grouped by day
  - Shows packing lists for multi-day trips
  - Persists user's previous plans for history
- **Key Functions**:
  - `display_plan()` — Renders plan steps with styling
  - `display_weather_info()` — Shows weather advisory
  - `_render_step()` — Formats individual task steps
  - `_save_plan()` — Persists plans to session history

### agent.py – PydanticAI Reasoning Core
- **Responsibility**: LLM orchestration + fallback planning
- **Key Features**:
  - Mandatory feasibility gate (location + activity validation)
  - Conditional weather fetching based on activity type
  - Single-plan generation (no Plan B alternatives)
  - Error handling with graceful fallback
- **Key Functions**:
  - `run_chronos()` — Main entry point (async)
  - `build_agent_prompt()` — Constructs LLM prompt with context
  - `parse_agent_response()` — Validates JSON output with Pydantic
  - `generate_fallback_response()` — Rule-based plan if LLM fails

### pipeline.py – 6-Stage Orchestration
- **Responsibility**: Validation + enrichment orchestration
- **Key Features**:
  - Location validation (geocoding)
  - Activity feasibility check
  - Parallel enrichment tasks (weather, user location, places)
  - Duration parsing
  - Context aggregation
  - Hand-off to planner_agent
- **Key Classes**:
  - `ChronosPipeline` — Main orchestrator
  - `DurationInfo` — Parsed duration with dates
  - `PlannerContext` — Data object passed to planner

### planner_agent.py – LLM Planning Schemas
- **Responsibility**: Output validation + prompt templates
- **Key Features**:
  - Pydantic models enforce LLM output structure
  - Prompt template for single-plan generation
  - Instructions to use real place names from OSM
  - Packing list guidance for multi-day trips
- **Key Classes**:
  - `TaskStep` — Individual plan step (order, time, location, risk)
  - `PlanOption` — Complete plan with steps + packing list
  - `PlannedOutput` — Final validated output (1 plan only)
  - `RiskLevel` — Enum (LOW, MEDIUM, HIGH, CRITICAL)

### models.py – Data Model Definitions
- **Responsibility**: Pydantic schemas for type safety
- **Key Classes**:
  - `ChronosResponse` — Full agent response
  - `PlanOption` — Plan structure with packing list
  - `TaskStep` — Individual task
  - `WeatherCondition` — Weather data
  - `TaskFeasibility` — Location + activity validation result
  - `AgentError` — Structured error handling
- **Key Feature**: Strict validation rejects malformed LLM output

### geocoding.py – Location Validation
- **Responsibility**: Map user location string to coordinates
- **APIs**: OpenStreetMap Nominatim (rate-limited at 1.05 sec/req)
- **Functions**:
  - `validate_location(city, state_or_country)` — Main entry point
  - `get_location_metadata(location)` — Terrain + country info
- **Fallback**: Mock database if API fails

### sanity_check.py – Activity Feasibility
- **Responsibility**: Block impossible activities
- **Rules**:
  - beach → requires coastal terrain
  - skiing → requires mountain terrain
  - desert safari → requires desert terrain
  - hiking, shopping → no restrictions
- **Function**: `check_activity_feasibility(activity, location)`

### weather_api.py – Weather Data
- **Responsibility**: Fetch or simulate weather
- **APIs**: wttr.in (or mock for simulation mode)
- **Functions**:
  - `fetch_weather()` — Get real forecast
  - `generate_simulated_weather()` — Deterministic mock data
  - `get_weather_summary()` — Human-friendly advice

### google_maps_integration.py – POI Discovery
- **Responsibility**: Find nearby places (actual tourist attractions)
- **APIs**: OpenStreetMap Overpass QL (distributed, no rate limit)
- **Class**: `GoogleMapsClient` (backed by OSM, not Google)
- **Method**: `find_nearby_places(lat, lon, types, radius)`
- **Returns**: List of `PlaceResult` with name, address, rating

### user_location.py – Geolocation + Travel Time
- **Responsibility**: Detect user location + estimate travel time
- **Function**: `detect_user_location(use_ip_geolocation=True)`
- **Returns**: `UserLocation` with city, country, coordinates

### tools.py & utils.py – Helper Functions
- Activity classification
- Weather risk scoring
- Date parsing
- Location formatting
- Weather advice generation

---

## Data Flow Example: Multi-Day Beach Trip

```
Input: "Beach vacation in Goa for 2 weeks"
   ↓
STAGE 1: Parse
   activity = "beach vacation"
   location = "Goa"
   duration_hint = "2 weeks"
   ↓
STAGE 2: Feasibility Check
   Geocoding: "Goa" → Valid (coastal)
   Activity Check: "beach" + coastal ✅ FEASIBLE
   ↓
STAGE 3: Enrichment (Parallel Tasks)
   Weather: Goa weather → "Pleasant, 28°C, low rain"
   User Location: User IP → Mumbai, 500 km away
   Travel Time: "4 hrs by car, 2 hrs flight"
   Places: Nominate Beaches → [Anjuna, Baga, Palolem]
           Restaurants → [Titos, Mango Tree, Peppy's]
           Temples → [Basilica of Bom Jesus, Se Cathedral]
   ↓
STAGE 4: Duration Logic
   Regex match: "2 weeks" → total_days=14
   start_date="2026-03-28"
   end_date="2026-04-10"
   ↓
STAGE 5: Context Preparation
   PlannerContext = {
       activity: "beach vacation",
       location_name: "Goa",
       duration: {total_days: 14, start: "2026-03-28", end: "2026-04-10"},
       weather: {temp: 28, condition: "clear", ...},
       weather_summary: "Pleasant tropical weather, bring sunscreen",
       travel_info: {origin: "Mumbai", distance_km: 500, ...},
       nearby_places: [
           {name: "Anjuna Beach", type: "beach", ...},
           {name: "Titos", type: "restaurant", ...},
           ...
       ],
       feasibility: {status: "FEASIBLE", reason: "Goa is coastal", ...}
   }
   ↓
STAGE 6: Hand-off to LLM Planner
   LLM uses PlannerContext to generate:
   
   Output:
   {
     "activity": "beach vacation",
     "location": "Goa",
     "total_days": 14,
     "plan_a": {
       "name": "Goa Beach Adventure",
       "summary": "Two-week coastal getaway with mix of beaches and culture",
       "steps": [
         {day: 1, time_from: "14:00", time_to: "16:00", 
          location: "Anjuna Beach", description: "Arrive and settle in..."},
         ...
       ],
       "packing_list": [
         "Lightweight summer clothing",
         "Sunscreen SPF 50+",
         "Hat and sunglasses",
         "Water shoes",
         "Refillable water bottle",
         ...
       ],
       "reasoning": "..."
     },
     "overall_risk": "low",
     "weather_note": "Pleasant weather, bring sunscreen for extended beach time"
   }
```

---

## API Integration Points

### To replace with real services:

**Geocoding (Nominatim → Google Maps)**:
```python
# In geocoding.py
async def geocode_location(city, state_or_country):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={city}"
    response = await httpx.AsyncClient().get(url, params={"key": GOOGLE_MAPS_KEY})
    data = response.json()["results"][0]
    return Location(latitude=data['lat'], longitude=data['lon'], ...)
```

**Places (Overpass → Google Places API)**:
```python
# In google_maps_integration.py
async def find_nearby_places(lat, lon, types, radius):
    url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    response = await httpx.AsyncClient().get(url, params={
        "location": f"{lat},{lon}",
        "radius": radius,
        "type": types[0],
        "key": GOOGLE_PLACES_KEY
    })
    return parse_places(response.json())
```

---

## Error Handling

**Fail-Fast Strategy**:
- Location invalid → Return error immediately
- Activity infeasible → Return error immediately
- Weather unavailable → Continue (informational only)
- OSM places unavailable → Continue with empty list
- LLM fails → Use fallback generator

**Fallback Generator** (`agent.py`):
- Generates rule-based plan if LLM crashes
- Same structure as LLM output
- Ensures demo stability

---

## Performance Considerations

- **Parallel Enrichment** (Stage 3): Weather + user location + places run concurrently
- **Rate Limiting**: Nominatim limited to 1.05 sec/request (respected globally)
- **Caching**: Weather cached for 30+ minutes locally
- **Async/Await**: Non-blocking I/O throughout pipeline
- **Single Thread**: Streamlit runs in single async loop (persistent thread)

---

## Testing & Simulation

**Simulation Mode** (`SIMULATION_MODE=true`):
- All APIs return deterministic mock data
- No external API calls
- Perfect for offline demos
- Reproducible results every run

**Test Files**:
- `test_guardrails.py` — 30+ unit tests for validation stages
- `integration_example.py` — Full pipeline walkthrough
- `sanity_check.py` — Contains assertion tests

---

## Security & Constraints

✅ **LLM Cannot**:
- Suggest impossible activities (checked by sanity_check)
- Make up weather (provided as pre-fetched data)
- Invent place names (restricted to OSM list)
- Output free-form text (Pydantic enforces schema)

✅ **Pipeline Cannot**:
- Skip location validation
- Skip activity feasibility check
- Call LLM before data enrichment
- Return unvalidated output

---

## Future Enhancements

1. Multi-language support (translate plans to user's language)
2. User authentication & persistent plan storage
3. Advanced rescheduling (move activities to avoid rain windows)
4. Real-time weather updates during trip
5. Group planning (multiple participants)
6. Mobile app integration
7. Calendar export (ICS/Google Calendar)
