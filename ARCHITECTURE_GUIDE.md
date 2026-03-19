"""
ARCHITECTURE_GUIDE.md - Chronos v2 Hallucination-Resistant Architecture

This document explains the guardrailed pipeline design and how to integrate it.
"""

# Chronos v2: Hallucination-Resistant Architecture

## Problem Statement

The original Chronos agent was prone to hallucinations:

1. **Impossible Plans**: Suggesting "beach day" in inland Anand
2. **Made-up Weather**: Inventing temperature/humidity when API fails
3. **Unconstrained Output**: LLM could output anything without validation

This v2 architecture adds **programmatic guardrails** at every stage.

---

## Architecture Overview

```
User Input
    ↓
[1] LOCATION VALIDATION (geocoding.py)
    ↓ (FAIL FAST if invalid)
[2] SANITY CHECK (sanity_check.py)
    ↓ (BLOCK impossible activities)
[3] WEATHER FETCH (weather_api.py)
    ↓ (Use mock or real API)
[4] PIPELINE ASSEMBLY (pipeline.py)
    ↓ (Package validated context)
[5] LLM PLANNING (planner_agent.py)
    ↓ (LLM generates plan with constraints)
[6] OUTPUT VALIDATION (Pydantic models)
    ↓ (REJECT invalid output)
Structured Plan (PlannedOutput)
```

---

## Stage 1: Location Validation (geocoding.py)

**Purpose**: Prevent planning for non-existent locations.

**How it works**:
- User provides location string (e.g., "Anand, India")
- `geocode_location()` looks up in database or real API
- Returns `Location` object with lat/lon + metadata (terrain_type, etc.)
- If not found → FAIL FAST (error returned immediately)

**Key Functions**:
- `geocode_location(city, state_or_country)` → Location | None
- `validate_location(city, state_or_country)` → (valid, Location, error_msg)
- `get_location_metadata(location)` → terrain info

**Mock Database**:
```python
MOCK_LOCATION_DATABASE = {
    ("anand", "india"): Location(..., terrain_type="plain"),
    ("goa", "india"): Location(..., terrain_type="coastal"),
    ("denver", "usa"): Location(..., terrain_type="mountain"),
}
```

**To plug in real API** (e.g., Google Maps, Nominatim):
```python
async def geocode_location(city, state_or_country):
    url = f"https://nominatim.openstreetmap.org/search?city={city}&..."
    response = await httpx.AsyncClient().get(url)
    data = response.json()
    return Location(
        name=data['display_name'],
        latitude=float(data['lat']),
        longitude=float(data['lon']),
        terrain_type=classify_terrain(data),  # Your classification logic
    )
```

---

## Stage 2: Sanity Check (sanity_check.py)

**Purpose**: Block geographically infeasible activities BEFORE LLM sees them.

**How it works**:
- Activity extracted from user input (e.g., "beach day" from "I want a beach day in Anand")
- `check_activity_feasibility(activity, location)` runs hardcoded rules
- **Hardcoded Rules** prevent hallucinations:
  ```
  "beach" requires ["coastal"] terrain
  "skiing" requires ["mountain"] terrain
  "desert safari" requires ["desert"] terrain
  ```
- If infeasible → return error immediately (no LLM call)
- If complex case → can delegate to LLM-based check (slower but flexible)

**Key Functions**:
- `check_activity_feasibility(activity, location)` → FeasibilityResult
- Returns: FEASIBLE | INFEASIBLE | REQUIRES_LLM_CHECK

**Example: "Beach day in Anand"**
```
Activity: "beach"
Location: Anand (terrain_type="plain")
Rules: "beach" requires "coastal"
Check: "coastal" in "plain"? NO
Result: INFEASIBLE ❌
Return error without calling LLM
```

**Example: "Hiking in Denver"**
```
Activity: "hiking"
Location: Denver (terrain_type="mountain")
Rules: "hiking" has no restrictions
Result: FEASIBLE ✅
Continue to next stage
```

**LLM-Based Fallback** (for complex cases):

If activity doesn't match hardcoded rules, you can ask LLM:
```
SANITY_CHECK_PROMPT_TEMPLATE = """
You are a geographic reasoning expert...
Is "{activity}" feasible at {location} ({terrain})?
Respond with ONLY JSON: {"feasible": true/false, "reason": "...", "suggestion": "..."}
"""
```

---

## Stage 3: Weather Fetch (weather_api.py)

**Purpose**: Get actual weather data (or simulated for demo).

**How it works**:
- Call `fetch_weather(location_name, lat, lon, forecast_date)`
- Returns `WeatherData` object with raw metrics
- Also generates human-friendly summary (no raw numbers to LLM)

**Key Functions**:
- `fetch_weather()` → WeatherData | None
- `generate_simulated_weather()` → WeatherData (deterministic for demos)
- `get_weather_summary(weather)` → str (human-readable advice)

**Mock Data**:
```python
MOCK_WEATHER_DATABASE = {
    ("goa, india", "2026-03-16"): WeatherData(
        temperature_celsius=30.8,
        condition="sunny",
        precipitation_chance=5,
        ...
    )
}
```

**To plug in real API** (e.g., OpenWeatherMap, WeatherAPI):
```python
async def fetch_weather(location_name, lat, lon, forecast_date):
    api_key = os.getenv("OPENWEATHER_API_KEY")
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        data = response.json()
    
    # Parse forecast for requested date
    forecast = [f for f in data['list'] if forecast_date in f['dt_txt']][0]
    return WeatherData(
        temperature_celsius=forecast['main']['temp'],
        condition=forecast['weather'][0]['main'],
        ...
    )
```

---

## Stage 4: Pipeline Assembly (pipeline.py)

**Purpose**: Orchestrate all guardrails and package context for LLM.

**Main Class**: `ChronosPipeline`

**Execution**:
```python
pipeline = ChronosPipeline(use_simulated_weather=True)
result = await pipeline.execute(
    activity="beach day",
    location_string="Goa, India",
    forecast_date="2026-03-16"
)

if result.success:
    context = result.context_for_planning  # Safe to pass to LLM
else:
    error = result.error  # Return to user
```

**Output** (if success):
```python
context_for_planning = {
    "activity": "beach day",
    "location": "Goa, India",
    "location_metadata": {
        "terrain_type": "coastal",
        "is_coastal": True,
        ...
    },
    "weather": {
        "raw": {
            "temperature_celsius": 30.8,
            "condition": "sunny",
            ...
        },
        "human_summary": "Sunny with light breeze. Wear sunscreen..."
    },
    "feasibility_check": {
        "status": "feasible",
        "reason": "Beach day at coastal Goa is feasible."
    }
}
```

---

## Stage 5: LLM Planning (planner_agent.py)

**Purpose**: Generate 2 plan options given validated context.

**LLM Constraints**:
- Can ONLY suggest activities already validated by pipeline
- Must use provided weather data (no making up metrics)
- OUTPUT MUST match `PlannedOutput` Pydantic schema
- No free-form text (all structured)

**Key Prompt Template**:

```
FINAL_PLANNER_PROMPT_TEMPLATE = """
You are Chronos, a weather-adaptive planning assistant.

LOCATION: {location_name}
TERRAIN: {terrain_type}
ACTIVITY: {activity}
WEATHER: {weather_data}

YOUR TASK:
1. Confirm "{activity}" is feasible at {location_name}
2. Create PLAN A (original plan, 4-6 time-bounded steps)
3. Create PLAN B (weather-optimized alternative, or null)
4. Assess overall risk (low/medium/high)
5. Provide weather advice (clothing, comfort, NOT raw metrics)

RESPOND WITH ONLY valid JSON (no markdown):
{
  "activity": "...",
  "location": "...",
  "feasible": true/false,
  "plan_a": { "name": "...", "summary": "...", "steps": [...] },
  "plan_b": { ... } or null,
  "overall_risk": "low|medium|high",
  "weather_note": "..."
}
"""
```

**Key Points**:
- Prompt is deterministic (no randomness)
- Weather data is provided, LLM can't hallucinate
- Output format is pre-defined (Pydantic validation)
- Human-friendly advice (NOT "15°C, 60% humidity")

---

## Stage 6: Output Validation (Pydantic)

**Purpose**: Reject invalid LLM output before showing to user.

**Validation Models**:
```python
class TaskStep(BaseModel):
    order: int = Field(ge=1)  # 1-indexed step number
    description: str  # What to do
    time_from: Optional[str]  # HH:MM format
    time_to: Optional[str]    # HH:MM format
    weather_sensitive: bool   # Is this affected by weather?
    risk_note: Optional[str]  # Weather warnings

class PlanOption(BaseModel):
    name: str                   # "Original Plan" or "Weather-Optimized"
    summary: str                # 1-2 sentence summary
    steps: list[TaskStep]       # Ordered steps
    reasoning: str              # Why this plan is good

class PlannedOutput(BaseModel):
    feasible: bool              # Can activity happen here?
    plan_a: PlanOption          # Required
    plan_b: Optional[PlanOption]  # Can be null
    overall_risk: RiskLevel     # LOW | MEDIUM | HIGH
    weather_note: str           # Human-friendly advice
```

**Validation happens automatically**:
```python
try:
    output = PlannedOutput(**llm_response_json)
    # Success — all fields valid
except ValidationError as e:
    print(f"LLM output rejected: {e}")
    # Return error to user
```

---

## Integration Example (integration_example.py)

**Main Function**: `plan_with_chronos_v2(activity, location_string, forecast_date, llm_client)`

**Usage**:
```python
result = await plan_with_chronos_v2(
    activity="beach day",
    location_string="Goa, India",
    forecast_date="2026-03-16",
    llm_client=None,  # Use mock if None
)

if result:
    print(f"Plan A: {result.plan_a.name}")
    print(f"Risk: {result.overall_risk}")
    for step in result.plan_a.steps:
        print(f"  {step.order}. {step.description}")
```

---

## How to Plug in Your APIs

### 1. Geocoding API

**Current**: Mock database in `geocoding.py`

**Replace with** (Nominatim example):
```python
async def geocode_location(city, state_or_country):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://nominatim.openstreetmap.org/search",
            params={"city": city, "format": "json"}
        )
    if response.status_code == 200:
        data = response.json()[0]
        return Location(
            name=data['display_name'],
            latitude=float(data['lat']),
            longitude=float(data['lon']),
            country=...,
            terrain_type=classify_terrain(float(data['lat']), float(data['lon'])),
        )
    return None
```

### 2. Weather API

**Current**: Mock database in `weather_api.py`

**Replace with** (OpenWeatherMap example):
```python
async def fetch_weather(location_name, lat, lon, forecast_date):
    api_key = os.getenv("OPENWEATHER_API_KEY")
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={"lat": lat, "lon": lon, "appid": api_key, "units": "metric"}
        )
    if response.status_code == 200:
        data = response.json()
        # Find forecast matching forecast_date and return WeatherData
    return None
```

### 3. LLM Integration

**Current**: Mock response in `integration_example.py`

**Replace with** (Gemini example):
```python
async def call_llm(prompt, llm_client=None):
    if llm_client is None:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        return response.text
    
    # Or pass your own client
    return await llm_client.generate(prompt)
```

---

## Key Features

✅ **Fail-Fast Location Validation**: Invalid locations rejected immediately  
✅ **Geographic Sanity Checks**: Impossible activities blocked before LLM  
✅ **Weather Data Control**: No hallucinated metrics (provided by pipeline)  
✅ **Structured Output**: Pydantic validation enforces schema  
✅ **Mock APIs**: Easy to test before plugging in real APIs  
✅ **Human-Friendly Advice**: No raw weather metrics to user  
✅ **Flexible Activity Rules**: Hardcoded rules + LLM-based fallback  
✅ **Modular Design**: Each stage independent, easy to replace  

---

## Testing

Run the integration example:
```bash
python integration_example.py
```

**Test Cases**:
1. Valid location + feasible activity (✅ should succeed)
2. Valid location + infeasible activity (❌ blocked by sanity check)
3. Invalid location (❌ blocked by geocoding)
4. Missing weather data (⚠️ continues with warning)

---

## Error Handling

All errors follow this pattern:
```python
@dataclass
class PipelineError:
    stage: str        # "location_validation", "sanity_check", etc.
    code: str         # "LOCATION_NOT_FOUND", "ACTIVITY_INFEASIBLE", etc.
    message: str      # User-friendly error message
    suggestion: str   # Helpful suggestion
```

Return `(success=False, error=PipelineError)` and let the UI handle it.

---

## Performance Notes

- **Pipeline**: ~100ms (mostly API calls)
- **LLM Planning**: ~2-5s (depends on model)
- **Validation**: ~10ms (Pydantic parsing)

Cache weather data if the same location is queried multiple times.
