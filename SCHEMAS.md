"""
SCHEMAS.md - Complete Data Schemas for Chronos v2

This document shows all Pydantic models and data structures used in the pipeline.
Use this for understanding input/output contracts.
"""

# Chronos v2 Data Schemas

## Overview

The entire pipeline uses strongly-typed Pydantic models. This ensures:
- Type safety (no unexpected field types)
- Validation (all data checked on creation)
- IDE autocomplete (you know what fields exist)
- Clear contracts (producer and consumer agree on structure)

---

## 1. Location Data (geocoding.py)

### Location (dataclass)

```python
@dataclass
class Location:
    name: str                      # "Anand, Gujarat, India"
    latitude: float                # 22.5585
    longitude: float               # 72.9297
    country: str                   # "India"
    state_or_region: str           # "Gujarat"
    continent: str                 # "Asia"
    terrain_type: str              # "coastal", "desert", "mountain", "plain", "urban", "forest"
    is_valid: bool = True
```

### Location Metadata (returned by get_location_metadata)

```python
{
    "name": "Anand, Gujarat, India",
    "latitude": 22.5585,
    "longitude": 72.9297,
    "country": "India",
    "state": "Gujarat",
    "continent": "Asia",
    "terrain_type": "plain",
    "is_coastal": False,
    "is_mountain": False,
    "is_desert": False,
    "is_urban": False,
}
```

---

## 2. Weather Data (weather_api.py)

### WeatherData (dataclass)

```python
@dataclass
class WeatherData:
    temperature_celsius: float      # 30.8
    condition: str                  # "sunny", "rainy", "cloudy", etc.
    precipitation_chance: int       # 0-100, probability %
    wind_speed_kmh: float          # 18.0
    humidity_percent: int          # 0-100
    uv_index: float                # 7.8
    forecast_date: str             # "2026-03-16"
    location_name: str             # "Goa, India"
```

---

## 3. Feasibility Check (sanity_check.py)

### FeasibilityStatus (Enum)

```python
class FeasibilityStatus(str, Enum):
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    REQUIRES_LLAMA_CHECK = "requires_llm_check"
```

### FeasibilityResult (dataclass)

```python
@dataclass
class FeasibilityResult:
    status: FeasibilityStatus      # One of: FEASIBLE, INFEASIBLE, REQUIRES_LLAMA_CHECK
    reason: str                    # "Beach day is feasible at coastal Goa"
    suggestion: Optional[str]      # "Try Goa instead", or None
```

---

## 4. Pipeline (pipeline.py)

### PipelineError (dataclass)

```python
@dataclass
class PipelineError:
    stage: str                     # "location_validation", "sanity_check", "weather_fetch", "planning"
    code: str                      # "LOCATION_NOT_FOUND", "ACTIVITY_INFEASIBLE", etc.
    message: str                   # Human-readable error message
    suggestion: Optional[str]      # Helpful suggestion for user
```

### PipelineResult (dataclass)

```python
@dataclass
class PipelineResult:
    success: bool                  # True if all checks passed
    error: Optional[PipelineError] # If success=False, contains error details
    
    # Populated only if success=True:
    location: Optional[Location]           # Geocoded location
    location_metadata: Optional[dict]      # Location metadata (terrain, coordinates, etc.)
    activity: Optional[str]                # User's activity
    forecast_date: Optional[str]           # Date for planning (YYYY-MM-DD)
    weather: Optional[WeatherData]         # Fetched weather data
    weather_summary: Optional[str]         # Human-friendly weather advice
    context_for_planning: Optional[dict]   # Ready-to-pass context for LLM
```

### Context For Planning (dict)

```python
context_for_planning = {
    "activity": "beach day",
    "location": "Goa, India",
    "location_metadata": {
        "name": "Goa, India",
        "terrain_type": "coastal",
        "latitude": 15.3667,
        "longitude": 73.8333,
        "country": "India",
        "state": "Goa",
        "continent": "Asia",
        "is_coastal": True,
        "is_mountain": False,
        "is_desert": False,
        "is_urban": False,
    },
    "activity": "beach day",
    "forecast_date": "2026-03-16",
    "weather": {
        "raw": {
            "temperature_celsius": 30.8,
            "condition": "sunny",
            "precipitation_chance": 5,
            "wind_speed_kmh": 18.0,
            "humidity_percent": 68,
            "uv_index": 7.8,
        },
        "human_summary": "Sunny with light breeze. Wear sunscreen and stay hydrated...",
    },
    "feasibility_check": {
        "status": "feasible",
        "reason": "Beach day at coastal Goa is feasible.",
    }
}
```

---

## 5. Planning Agent Output (planner_agent.py)

### TaskStep (Pydantic BaseModel)

```python
class TaskStep(BaseModel):
    order: int                     # 1, 2, 3, ... (1-indexed, must be ordered)
    description: str               # "Pack sunscreen and swimsuit" (10-500 chars)
    time_from: Optional[str]       # "08:00" (HH:MM format) or None
    time_to: Optional[str]         # "08:30" (HH:MM format) or None
    location: Optional[str]        # "Home" or None
    weather_sensitive: bool        # Is this step affected by weather?
    risk_note: Optional[str]       # "Stay in shade—high UV" or None
```

### PlanOption (Pydantic BaseModel)

```python
class PlanOption(BaseModel):
    name: str                      # "Original Beach Day" or "Weather-Optimized Alternative"
    summary: str                   # One or two sentence summary (20-200 chars)
    steps: list[TaskStep]          # 1-50 steps
    reasoning: str                 # Why this plan works (50-500 chars)
```

### RiskLevel (Enum)

```python
class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
```

### PlannedOutput (Pydantic BaseModel)

**THIS IS THE FINAL OUTPUT THAT REACHES THE USER** ✅

```python
class PlannedOutput(BaseModel):
    # Metadata
    activity: str                  # "beach day"
    location: str                  # "Goa, India"
    date: str                      # "2026-03-16" (YYYY-MM-DD)
    
    # Feasibility assessment
    feasible: bool                 # True or False
    feasibility_note: str          # "Goa is a coastal state with excellent beaches" (10-300 chars)
    
    # Plans
    plan_a: PlanOption             # REQUIRED (original plan)
    plan_b: Optional[PlanOption]   # OPTIONAL (weather-optimized alternative, can be null)
    
    # Overall assessment
    overall_risk: RiskLevel        # LOW, MEDIUM, or HIGH
    weather_note: str              # Human-friendly weather advice (20-300 chars)
    
    # Example:
    # {
    #   "activity": "beach day",
    #   "location": "Goa, India",
    #   "date": "2026-03-16",
    #   "feasible": true,
    #   "feasibility_note": "Goa is a coastal state perfect for beach activities",
    #   "plan_a": {
    #     "name": "Classic Beach Day",
    #     "summary": "Sunrise swimming, beach relaxation, sunset dinner",
    #     "steps": [
    #       {
    #         "order": 1,
    #         "description": "Pack sunscreen, hat, swimsuit at 7am",
    #         "time_from": "07:00",
    #         "time_to": "07:30",
    #         "location": "Hotel",
    #         "weather_sensitive": false,
    #         "risk_note": null
    #       },
    #       ...
    #     ],
    #     "reasoning": "Perfect weather for beach activities"
    #   },
    #   "plan_b": null,
    #   "overall_risk": "low",
    #   "weather_note": "Sunny with light breeze. Wear sunscreen and stay hydrated."
    # }
```

---

## 6. Complete Example: Data Flow

### INPUT
```python
user_input = {
    "activity": "beach day",
    "location": "Goa, India",
    "forecast_date": "2026-03-16"
}
```

### After Pipeline (PipelineResult with success=True)
```python
{
    "success": True,
    "location": Location(name="Goa, India", latitude=15.3667, ...),
    "location_metadata": {"terrain_type": "coastal", ...},
    "activity": "beach day",
    "forecast_date": "2026-03-16",
    "weather": WeatherData(temperature_celsius=30.8, condition="sunny", ...),
    "weather_summary": "Sunny with light breeze...",
    "context_for_planning": { ... }  # Passed to LLM
}
```

### After LLM Planning (PlannedOutput)
```python
{
    "activity": "beach day",
    "location": "Goa, India",
    "date": "2026-03-16",
    "feasible": True,
    "feasibility_note": "Goa is a coastal state perfect for beach activities",
    "plan_a": {
        "name": "Classic Beach Day",
        "summary": "Relax and swim at the beach",
        "steps": [
            {
                "order": 1,
                "description": "Pack beach essentials (sunscreen, hat, swimsuit)",
                "time_from": "07:00",
                "time_to": "07:30",
                "location": "Hotel",
                "weather_sensitive": False,
                "risk_note": None
            },
            {
                "order": 2,
                "description": "Drive to Calangute Beach",
                "time_from": "08:00",
                "time_to": "08:30",
                "location": "Car",
                "weather_sensitive": False,
                "risk_note": None
            },
            {
                "order": 3,
                "description": "Swim and relax at the beach",
                "time_from": "09:00",
                "time_to": "12:00",
                "location": "Calangute Beach",
                "weather_sensitive": True,
                "risk_note": "Wear sunscreen—high UV index. Stay in shade periodically."
            },
            {
                "order": 4,
                "description": "Lunch at beachside cafe",
                "time_from": "12:30",
                "time_to": "13:30",
                "location": "Beachside Cafe",
                "weather_sensitive": False,
                "risk_note": None
            },
            {
                "order": 5,
                "description": "Relax on the beach",
                "time_from": "14:00",
                "time_to": "17:00",
                "location": "Beach",
                "weather_sensitive": False,
                "risk_note": "Stay in shade—manage sun exposure"
            },
            {
                "order": 6,
                "description": "Sunset dinner at beachfront restaurant",
                "time_from": "18:00",
                "time_to": "20:00",
                "location": "Beachfront Restaurant",
                "weather_sensitive": False,
                "risk_note": None
            }
        ],
        "reasoning": "This plan maximizes beach time while managing UV exposure through strategic timing"
    },
    "plan_b": null,
    "overall_risk": "low",
    "weather_note": "Sunny with light ocean breeze. You'll feel warm and comfortable in light clothing. Bring sunscreen and reapply every two hours. The breeze will keep you cool."
}
```

---

## Validation Rules (Pydantic)

### TaskStep Validation
- `order`: Must be >= 1
- `description`: Length must be 10-500 characters
- `time_from`, `time_to`: Must match HH:MM format if provided
- `steps` in PlanOption: Must be in correct order (1, 2, 3, ...) with no gaps

### PlanOption Validation
- `name`: Max 50 characters
- `summary`: 20-200 characters
- `steps`: 1-50 items
- `reasoning`: 50-500 characters
- Steps must be ordered correctly (1 to N with no gaps)

### PlannedOutput Validation
- `date`: Must be YYYY-MM-DD format
- `feasible`: Must be boolean
- `plan_a`: Required, must be valid PlanOption
- `plan_b`: Optional, can be null or valid PlanOption
- `overall_risk`: Must be one of RiskLevel values
- `feasibility_note`, `weather_note`: String length limits

---

## Common Validation Errors

### Error: "Steps must be ordered 1 to N"
**Cause**: Step orders are not sequential (e.g., 1, 2, 4 instead of 1, 2, 3)  
**Fix**: Ensure LLM generates steps with consecutive order numbers

### Error: "Plan cannot have more than 50 steps"
**Cause**: LLM generated too many steps  
**Fix**: Instruct LLM to create 4-6 steps, not more

### Error: "Missing required fields in plan_a"
**Cause**: LLM output is missing required fields (name, summary, steps, reasoning)  
**Fix**: Ensure LLM prompt includes all required fields in JSON template

### Error: "Invalid value for overall_risk"
**Cause**: LLM returned risk level that's not "low", "medium", or "high"  
**Fix**: Instruct LLM to use exact values from RiskLevel enum

---

## Using Schemas in Your Code

### Parse and Validate LLM Output
```python
import json
from planner_agent import PlannedOutput

llm_response = """{"activity": "beach day", ..., "plan_a": {...}, "plan_b": null, ...}"""

try:
    output = PlannedOutput(**json.loads(llm_response))
    print(f"✅ Valid output")
    print(f"   Activity: {output.activity}")
    print(f"   Risk: {output.overall_risk}")
except Exception as e:
    print(f"❌ Invalid output: {e}")
```

### Access nested data safely
```python
# Because of Pydantic, all fields are guaranteed to exist and have correct types
for step in output.plan_a.steps:
    print(f"Step {step.order}: {step.description}")
    if step.weather_sensitive:
        print(f"  ⚠️ Weather note: {step.risk_note}")
```

### Serialize to JSON (for storage/transmission)
```python
output_json = output.model_dump_json(indent=2)
# Guaranteed to always match the schema
```

---

## Type Safety Benefits

Because we use Pydantic:

✅ IDE autocompletion works (you see all available fields)  
✅ Type checking catches errors (mypy integration)  
✅ Validation on creation (bad data rejected immediately)  
✅ Serialization/deserialization built-in  
✅ Clear contracts between components  
✅ Easy to test (mock objects match schema exactly)  

---

## Next Steps

Use these schemas to:
1. Understand the data flow through the pipeline
2. Debug LLM output (check what was expected vs what was received)
3. Extend the system (add new fields to models)
4. Write tests (create mock objects matching these structures)
5. Build UI (display planner agent response with type safety)
