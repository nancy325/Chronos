"""
QUICK_START.md - Get the hallucination-resistant pipeline running in 5 minutes
"""

# Quick Start: Chronos v2 Hallucination-Resistant Pipeline

## What You Get

- ✅ **Location Validation**: Reject invalid locations (fail-fast)
- ✅ **Sanity Check**: Block infeasible activities (beach in Anand = no)
- ✅ **Weather Data**: Mock API (replace with real later)
- ✅ **LLM Planning**: Structured output with Pydantic validation
- ✅ **Prompt Templates**: Exact prompts for Sanity Check + Final Planner

## Files Created

```
geocoding.py          - Location validation + geocoding (mock database)
weather_api.py        - Weather fetching (mock database)
sanity_check.py       - Geographic feasibility checks + SANITY_CHECK_PROMPT_TEMPLATE
planner_agent.py      - LLM output contracts + FINAL_PLANNER_PROMPT_TEMPLATE
pipeline.py           - Main orchestration (all guardrails)
integration_example.py - Full working example + EXACT PROMPT TEMPLATES
ARCHITECTURE_GUIDE.md - Deep dive on design
```

## How to Test

### 1. Run the Integration Example

```bash
cd d:\Chronos\Chronos
python integration_example.py
```

**Output**:
```
✅ Location validated: Goa, India
✅ Activity feasible: beach day
✅ Weather available: sunny
✅ Generated 3 steps for Plan A
```

### 2. Test Individual Modules

**Test location validation**:
```python
from geocoding import validate_location

is_valid, location, error = validate_location("Goa", "India")
print(location.name)  # "Goa, India"
print(location.terrain_type)  # "coastal"
```

**Test sanity check**:
```python
from geocoding import validate_location
from sanity_check import check_activity_feasibility

_, location, _ = validate_location("Anand", "India")
result = check_activity_feasibility("beach", location)
print(result.status)  # FeasibilityStatus.INFEASIBLE
print(result.reason)  # "beach is not feasible in plain terrain..."
```

**Test pipeline**:
```python
import asyncio
from pipeline import run_planning_pipeline

async def test():
    success, context, error = await run_planning_pipeline(
        activity="beach day",
        location_string="Goa, India",
        forecast_date="2026-03-16",
        use_simulated_weather=True
    )
    
    if success:
        print(context['location'])
        print(context['weather']['human_summary'])
    else:
        print(f"Error: {error.message}")

asyncio.run(test())
```

## The Exact Prompts

### SANITY CHECK Prompt

Used when activity needs geographic validation:

```python
from sanity_check import SANITY_CHECK_PROMPT_TEMPLATE

prompt = SANITY_CHECK_PROMPT_TEMPLATE.format(
    location_name="Anand, Gujarat, India",
    terrain_type="plain",
    latitude=22.5585,
    longitude=72.9297,
    country="India",
    state="Gujarat",
    activity="beach swimming"
)
```

**Template**:
```
You are a geographic reasoning expert. Your job is to validate whether an activity is physically possible at a given location.

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
{
  "feasible": true or false,
  "reason": "Short explanation of why it's feasible or not",
  "suggestion": "If infeasible, suggest an alternative location. If feasible, set to null."
}

...
```

### FINAL PLANNER Prompt

Used to generate the actual plan:

```python
from planner_agent import FINAL_PLANNER_PROMPT_TEMPLATE

prompt = FINAL_PLANNER_PROMPT_TEMPLATE.format(
    activity="beach day",
    location_name="Goa, India",
    terrain_type="coastal",
    country="India",
    latitude=15.3667,
    longitude=73.8333,
    forecast_date="2026-03-16",
    weather_data="""
Temperature: 30.8°C
Condition: sunny
Precipitation Chance: 5%
Wind Speed: 18.0 km/h
Humidity: 68%
UV Index: 7.8

Human-Friendly Summary: Sunny with light breeze. Wear sunscreen and stay hydrated...
"""
)
```

**Template**:
```
You are Chronos, a weather-adaptive planning assistant.

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
{
  "activity": "{activity}",
  "location": "{location_name}",
  "date": "{forecast_date}",
  "feasible": true or false,
  "feasibility_note": "Why this activity is feasible here...",
  "plan_a": {
    "name": "Original Beach Day",
    "summary": "Traditional beach day with relaxation and swimming",
    "steps": [
      {
        "order": 1,
        "description": "Pack sunscreen, swimsuit, and water bottle",
        "time_from": "08:00",
        "time_to": "08:30",
        "location": "Home",
        "weather_sensitive": false,
        "risk_note": null
      },
      ...more steps...
    ],
    "reasoning": "This plan works well given the weather because..."
  },
  "plan_b": { ... } or null,
  "overall_risk": "low" or "medium" or "high",
  "weather_note": "It'll be warm and sunny, so bring sunscreen and stay hydrated..."
}
```

## Plugging in Your APIs

### 1. Google Maps Geocoding

Edit `geocoding.py`:
```python
async def geocode_location(city, state_or_country):
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={city}&key={api_key}"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
    
    data = response.json()['results'][0]
    return Location(
        name=data['formatted_address'],
        latitude=data['geometry']['location']['lat'],
        longitude=data['geometry']['location']['lng'],
        ...
    )
```

### 2. OpenWeatherMap

Edit `weather_api.py`:
```python
async def fetch_weather(location_name, lat, lon, forecast_date):
    api_key = os.getenv("OPENWEATHER_API_KEY")
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
    
    data = response.json()
    # Parse forecast for requested date
    return WeatherData(...)
```

### 3. Gemini LLM

Edit `integration_example.py`:
```python
async def call_llm(prompt, llm_client=None):
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)
    return response.text
```

## Typical Pipeline Flow

```
1. User: "I want a beach day in Anand on March 16"
   ↓
2. GEOCODING: Validate "Anand, India" → Location(terrain="plain") ✅
   ↓
3. SANITY CHECK: Beach requires coastal, but Anand is plain
   → INFEASIBLE ❌
   → Return error: "Beach day not possible in inland Anand. Try Goa instead."

---

1. User: "I want a beach day in Goa on March 16"
   ↓
2. GEOCODING: Validate "Goa, India" → Location(terrain="coastal") ✅
   ↓
3. SANITY CHECK: Beach requires coastal, Goa is coastal
   → FEASIBLE ✅
   ↓
4. WEATHER: Fetch weather for Goa → sunny, 30.8°C ✅
   ↓
5. PIPELINE: Build context with location + weather ✅
   ↓
6. LLM: Generate Plan A (beach) + Plan B (if needed)
   → Validated against Pydantic schema ✅
   ↓
7. USER: Returns 2 plans with time-bounded steps and weather advice
```

## Error Messages to User

**Location not found**:
```
❌ Error: Location 'FakeCity' not found
Suggestion: Did you mean: Mumbai, Delhi, Bangalore?
```

**Activity infeasible**:
```
❌ Error: Beach day not feasible in plain terrain
Location: Anand, Gujarat is inland with no beaches
Suggestion: Try Goa or Mumbai (nearby coastal cities)
```

**Weather unavailable**:
```
⚠️ Weather data unavailable for this date
Planning will proceed with general activity recommendations
(no rain/temperature constraints)
```

## Next Steps

1. Copy these 6 files to your Chronos project
2. Run `python integration_example.py` to test
3. Plug in your real Geocoding API (Google, Nominatim)
4. Plug in your real Weather API (OpenWeatherMap, WeatherAPI)
5. Plug in your LLM (Gemini, Claude, etc.)
6. Integrate into your Streamlit app

## Key Takeaways

✅ **Guardrails prevent hallucinations at every stage**
✅ **Fail-fast on invalid locations**
✅ **Block infeasible activities before LLM**
✅ **Use mock APIs for easy testing**
✅ **Exact prompt templates provided (copy-paste ready)**
✅ **Pydantic validation enforces output schema**
✅ **Modular design makes it easy to plug in real APIs**
