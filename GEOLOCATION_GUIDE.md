# Chronos v2.1: Geolocation & Travel Planning Guide

## Overview

Chronos v2.1 adds intelligent geolocation-aware planning with Google Maps integration, enabling:
- **Auto-detection** of user's current location (IP-based or GPS)
- **Travel time estimation** from user to destination
- **Nearby attraction discovery** at destination
- **Location-based itinerary optimization** (activities grouped by proximity)

## OpenStreetMap Geocoding Integration (NEW)

Chronos now integrates OpenStreetMap geocoding via **Nominatim Search API** for live location resolution:

- Converts user-provided location text → **Latitude / Longitude**
- Uses public OSM geocoding endpoint: `https://nominatim.openstreetmap.org/search`
- Uses policy-safe request headers (`User-Agent`) and conservative rate limiting
- Falls back safely if network/API is unavailable

### Important correction to common OSM API example

Calling `http://wiki.openstreetmap.org/wiki/API` and then doing `response.json()` is not valid geocoding and usually does not return geocoding JSON.

Use Nominatim Search instead (forward geocoding), with parameters like:
- `q=<location text>`
- `format=jsonv2`
- `limit=1` (or more for suggestions)
- `addressdetails=1`

### Nearest valid places on impossible requests

If Chronos cannot validate a location, it now returns nearest/relevant place suggestions by:
1. Local known-location matches (fast deterministic fallback)
2. Nominatim top matches with coordinates

This means invalid requests now produce useful alternatives instead of a dead-end error.

## Architecture Expansion: 4 → 6 Stages

### Original 4-Stage Pipeline (v2.0)
```
Stage 1: Location Validation (geocoding) → FAIL FAST
Stage 2: Sanity Check (geography) → BLOCK impossible activities  
Stage 3: Weather Fetch (API) → Get actual data
Stage 4: Context Assembly → Prepare LLM prompt
```

### New 6-Stage Pipeline (v2.1)

```
┌─────────────────────────────────────────────────────────────┐
│                    CHRONOS v2.1 PIPELINE                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ STAGE 1: LOCATION VALIDATION                               │
│   └─ validate_location(city, country)                      │
│   └─ Check: Is destination real and accessible?            │
│   └─ Fail-fast if not found in database                    │
│   └─ Result: Location object with coordinates + terrain    │
│                                                             │
│ STAGE 2: SANITY CHECK                                      │
│   └─ check_activity_feasibility(activity, location)        │
│   └─ Check: Does location's terrain support activity?      │
│   └─ Example: Beach requires coastal, skiing requires mtn  │
│   └─ Result: Feasibility status or error                   │
│                                                             │
│ STAGE 3: WEATHER DATA                                      │
│   └─ fetch_weather(location, date)                         │
│   └─ Get: Actual or simulated weather data                 │
│   └─ Result: WeatherData with human-friendly summary       │
│                                                             │
│ ┌─ NEW IN v2.1 ────────────────────────────────────────┐  │
│ │ STAGE 4: USER GEOLOCATION & TRAVEL TIME              │  │
│ │   └─ detect_user_location() → IP-based geolocation   │  │
│ │   └─ Result: UserLocation (city, lat, lon, timezone) │  │
│ │   └─ get_travel_time_estimate(origin, dest)          │  │
│ │   └─ Result: Distance + duration category             │  │
│ │                                                        │  │
│ │ STAGE 5: NEARBY PLACES & CLUSTERING                  │  │
│ │   └─ GoogleMapsClient.find_nearby_places()            │  │
│ │   └─ Get: Restaurants, museums, shops, attractions    │  │
│ │   └─ Cluster: Group by proximity (2km default)        │  │
│ │   └─ Result: [NearbyPlace] sorted by rating           │  │
│ │                                                        │  │
│ │ STAGE 6: ENHANCED CONTEXT ASSEMBLY                    │  │
│ │   └─ Merge travel_info + nearby_places                │  │
│ │   └─ Prepare rich context for LLM                     │  │
│ │   └─ Include activity type suggestions                │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                             │
│ STAGE 7: LLM PLANNING (with guardrails)                    │
│   └─ get_final_planner_prompt(context)                     │
│   └─ Input: All validated data + nearby places             │
│   └─ Output: PlannedOutput (structured JSON)               │
│                                                             │
│ STAGE 8: OUTPUT VALIDATION                                  │
│   └─ Pydantic validation of LLM response                   │
│   └─ Ensures: Schema compliance, time constraints          │
│   └─ Result: PlannedOutput or error                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## New Modules

### 1. `user_location.py` - Geolocation Detection

**Purpose:** Detect user's current location using IP address

**Key Functions:**
```python
async def detect_user_location() -> UserLocation:
    """
    Detect user's current location via IP geolocation.
    
    Returns:
        UserLocation(
            city: str           # e.g., "Nadiād"
            country: str        # e.g., "India"
            latitude: float
            longitude: float
            timezone: str       # e.g., "Asia/Kolkata"
            isp: str           # e.g., "Jio"
            accuracy_note: str # e.g., "City-level (±50km)"
        )
    """
```

**API Used:**
- **Primary:** `ip-api.com` (free tier, 45 req/min, city-level accuracy)
- **Fallback:** Hardcoded Delhi location for demos

**Accuracy:**
- **IP Geolocation:** City-level (~50km radius)
- **Browser GPS:** Street-level (~10m radius) - optional enhancement
- **Hybrid:** Use GPS if available, fallback to IP

**Usage Example:**
```python
user_loc = await detect_user_location()
print(f"You are in {user_loc.city}, {user_loc.country}")
print(f"Timezone: {user_loc.timezone}")
print(f"Accuracy: {user_loc.accuracy_note}")
```

---

### 2. `google_maps_integration.py` - Maps API Wrapper

**Purpose:** Google Maps Distance Matrix & Places APIs integration

**Key Classes & Methods:**

#### GoogleMapsClient
```python
class GoogleMapsClient:
    """Wrapper for Google Maps APIs with mock fallback."""
    
    async def get_distance_matrix(
        origins: List[Location],
        destinations: List[Location],
        mode: str = "driving"
    ) -> List[TravelRoute]:
        """Get travel time/distance between locations."""
        # Returns: [TravelRoute(origin, dest, distance_km, duration_minutes, mode)]
    
    async def find_nearby_places(
        location: Location,
        activity_types: List[str],  # ["restaurant", "museum", "beach"]
        radius_meters: int = 5000
    ) -> List[NearbyPlace]:
        """Find nearby attractions/restaurants/shops."""
        # Returns: [NearbyPlace] sorted by rating
    
    async def optimize_day_itinerary(
        activities: List[str],
        destination: Location,
        user_location: UserLocation
    ) -> str:
        """Suggest optimal day itinerary considering travel time."""
        # Returns: Formatted itinerary text
```

**Data Models:**
```python
@dataclass
class TravelRoute:
    origin_name: str        # "Nadiād, India"
    dest_name: str          # "Goa, India"
    distance_km: float      # 820.1
    duration_minutes: int   # 480 (8 hours)
    mode: str               # "flight" / "drive" / "transit"

@dataclass
class NearbyPlace:
    name: str               # "Coastal Kitchen"
    place_type: str         # "restaurant"
    latitude: float
    longitude: float
    rating: float           # 4.5
    distance_meters: int    # 250
    place_id: str           # Google Place ID
    address: str            # Full address
```

**Activity Type Mapping:**
```python
ACTIVITY_TYPE_MAP = {
    "beach": ["beach", "restaurant", "shopping_mall"],
    "hiking": ["hiking_trail", "restaurant", "viewpoint"],
    "cultural": ["museum", "historical_site", "restaurant"],
    "dining": ["restaurant", "cafe", "bar"],
    # ... more mappings
}
```

**API Setup:**
1. Go to [Google Cloud Console](https://cloud.google.com/console)
2. Enable these APIs:
   - Distance Matrix API
   - Places API
   - Geocoding API
3. Create API key
4. Set environment variable: `GOOGLE_MAPS_API_KEY=your_key_here`
5. Set up billing (free tier: 25,000 requests/day)

**Mock Responses (No API Key Needed):**
The module includes hardcoded mock responses for testing:
- Distances calculated using Haversine formula
- Nearby places: Pre-defined attractions for demo locations
- Ratings: Realistic 4.0-4.8 star ratings

**Usage Without API Key:**
```python
api_key = os.getenv("GOOGLE_MAPS_API_KEY")
if api_key:
    client = GoogleMapsClient(api_key)  # Real API
else:
    client = GoogleMapsClient()          # Mocks (works without key)
```

---

### 3. Updated `pipeline.py` - 6-Stage Orchestration

**New Stages Added (4 & 5):**

```python
async def execute(
    activity: str,
    location_string: str,      # "Goa, India"
    forecast_date: str         # "2026-03-16"
) -> PipelineResult:
    
    # STAGE 1: Parse & validate location
    parts = location_string.split(",")
    is_valid, location = validate_location(parts[0], parts[1])
    
    # STAGE 2: Sanity check activity
    feasibility = check_activity_feasibility(activity, location)
    
    # STAGE 3: Fetch weather
    weather = fetch_weather(location, forecast_date)
    
    # ──── NEW IN v2.1 ────
    
    # STAGE 4: Detect user location & travel time
    user_location = await detect_user_location()
    distance_km = _calculate_distance(user_location, location)
    travel_info = {
        "origin": f"{user_location.city}, {user_location.country}",
        "destination": location.name,
        "distance_km": distance_km,
        "description": get_travel_time_estimate(distance_km),
        "mode": "flight" if distance_km > 500 else "drive"
    }
    
    # STAGE 5: Find nearby places & cluster
    activity_types = _extract_activity_types(activity)
    nearby = await maps_client.find_nearby_places(
        location, activity_types, radius_meters=5000
    )
    
    # STAGE 6: Assemble rich context
    context = {
        "location": location.name,
        "activity": activity,
        "forecast_date": forecast_date,
        "weather": weather,
        "location_metadata": get_location_metadata(location),
        "user_location": user_location,  # NEW
        "travel_info": travel_info,      # NEW
        "nearby_places": nearby          # NEW
    }
    
    # ──────────────────────
    
    return PipelineResult(
        success=True,
        location=location,
        user_location=user_location,     # NEW
        travel_info=travel_info,         # NEW
        nearby_places=nearby,            # NEW
        context_for_planning=context
    )
```

**PipelineResult Extended:**
```python
@dataclass
class PipelineResult:
    # Existing fields
    success: bool
    error: Optional[PipelineError]
    location: Optional[Location]
    activity: Optional[str]
    weather: Optional[WeatherData]
    
    # NEW in v2.1
    user_location: Optional[UserLocation] = None
    travel_info: Optional[dict] = None
    nearby_places: Optional[List] = None
```

---

## Travel Estimation Algorithm

### Distance Categories → Travel Mode & Time

```python
def get_travel_time_estimate(distance_km: float) -> str:
    if distance_km < 10:
        return f"~{int(distance_km/5)} min walk"
    elif distance_km < 50:
        return f"~{int(distance_km/60)} min drive (short)"
    elif distance_km < 200:
        return f"~{int(distance_km/80)} hours drive (medium)"
    elif distance_km < 500:
        return f"~{int(distance_km/100)} hours drive (long)"
    else:
        return f"~{int(distance_km/900)} hours flight (+ connections)"
```

### Proximity Clustering Algorithm

Groups nearby places by 2km distance threshold:

```python
def _cluster_by_proximity(
    places: List[NearbyPlace],
    threshold_km: float = 2.0
) -> Dict[int, List[NearbyPlace]]:
    """
    Group places by proximity.
    
    Uses simple centroid-based clustering:
    1. Sort places by distance from destination
    2. Create clusters of places within threshold
    3. Each cluster is a stop in the day itinerary
    """
```

**Example Clustering:**
```
Destination: Goa Beach

Cluster 1 (Beach area - 0-500m):
  ✓ Calangute Beach (beach)
  ✓ Coastal Kitchen (restaurant, 200m)
  ✓ Beach Shack Cafe (restaurant, 400m)

Cluster 2 (Market area - 2-3km):
  ✓ Central Shopping Complex (mall, 2.1km)
  ✓ Waterfront Market (market, 2.5km)
  ✓ Local Curry House (restaurant, 2.2km)

→ Day plan: Travel (6h) → Beach area (2h) → Lunch → Market area (1h)
```

---

## Usage Examples

### Example 0: Geocode + Suggestions (OpenStreetMap)

Input:
- `city="Reykjavik"`, `state_or_country="Iceland"`

Resolved output (example):
```
{
    "name": "Reykjavík, Capital Region, Iceland",
    "latitude": 64.1466,
    "longitude": -21.9426,
    "country": "Iceland",
    "state_or_region": "Capital Region"
}
```

Invalid input example:
- `city="Anad"`

Returned error (example):
```
Location 'Anad' not found in database. Did you mean: Anand, Gujarat, India (22.5585, 72.9297), Vadodara, Gujarat, India (22.3072, 73.1812)?
```

### Example 1: Basic Integration (with Mock API)

```python
import asyncio
from integration_with_geolocation_example import plan_with_geolocation

async def main():
    result = await plan_with_geolocation(
        activity="beach day with dining",
        destination_location="Goa, India",
        forecast_date="2026-03-16"
    )
    
    if result:
        print(f"Plan: {result.plan_a.summary}")
        for step in result.plan_a.steps:
            print(f"  {step.order}. {step.description} at {step.location}")

asyncio.run(main())
```

**Output:**
```
✅ Pipeline validation passed!
📍 Your Current Location: Nadiād, India
✈️ Travel Information:
   From: Nadiād, India
   To: Goa, India
   Distance: 820.1 km
   Duration: ~0 hours flight (+ connections)

🏪 Nearby Places at Destination:
   1. Coastal Kitchen (restaurant) ⭐ 4.5
   2. Beach Shack Cafe (restaurant) ⭐ 4.2
   3. Central Shopping Complex (shopping_mall) ⭐ 4.5

📅 COMPLETE DAY PLAN
🎯 Beach Day With Dining at Goa, India

Plan A: Beach Day with Local Cuisine
  1. Travel to Goa from Delhi (flight + hotel check-in) at 08:00-14:00
  2. Rest and freshen up at hotel at 14:00-15:30
  3. Visit Calangute Beach for swimming at 15:30-18:00
  4. Dinner at Coastal Kitchen at 18:30-20:00
  5. Evening walk at Beach Shack Cafe at 20:00-21:30
```

### Final planning context now includes coordinates

Chronos final planning context includes geocoded coordinates to drive downstream planning:

```
{
    "location": "Goa, India",
    "location_metadata": {
        "name": "Goa, India",
        "latitude": 15.3667,
        "longitude": 73.8333,
        "country": "India",
        "state": "Goa"
    },
    "travel_info": {
        "origin": "Delhi, India",
        "destination": "Goa, India",
        "distance_km": 1491.2,
        "mode": "flight"
    }
}
```

### Example 2: Using Google Maps Client Directly

```python
from google_maps_integration import GoogleMapsClient, Location
from user_location import detect_user_location
import asyncio

async def explore_destination():
    # Initialize client (auto-detects API key or uses mocks)
    client = GoogleMapsClient()
    
    # Get user location
    user_loc = await detect_user_location()
    print(f"Your location: {user_loc.city}")
    
    # Define destination
    dest = Location(
        name="Goa, India",
        latitude=15.3667,
        longitude=73.8333,
        place_id="ChIJ...",
        google_place_type="locality"
    )
    
    # Find nearby restaurants
    restaurants = await client.find_nearby_places(
        dest,
        activity_types=["restaurant"],
        radius_meters=3000
    )
    
    print(f"\nTop restaurants near {dest.name}:")
    for place in restaurants[:5]:
        print(f"  ⭐ {place.rating} - {place.name}")
        print(f"     {place.distance_meters}m away - {place.address}")

asyncio.run(explore_destination())
```

### Example 3: Real API Key Setup

```bash
# 1. Get API key from Google Cloud Console
# 2. Set environment variable (Windows)
set GOOGLE_MAPS_API_KEY=AIzaSyD...your_key_here

# 3. Or set in Python
import os
os.environ["GOOGLE_MAPS_API_KEY"] = "AIzaSyD...your_key_here"

# 4. Script automatically uses real API
python integration_with_geolocation_example.py
```

---

## Geolocation Accuracy

### Current Method: IP-Based (ip-api.com)

| Aspect | Details |
|--------|---------|
| **Accuracy** | City-level (~50km radius) |
| **API** | ip-api.com (free tier) |
| **Rate Limit** | 45 requests/minute |
| **Fallback** | Delhi hardcoded |
| **Setup** | None required |
| **Cost** | Free |

### Optional Enhancement: Browser GPS

For higher accuracy, add browser Geolocation API:

```python
# user_location.py (enhanced)
async def detect_user_location_hybrid() -> UserLocation:
    """
    Try GPS first (street-level), fallback to IP (city-level).
    """
    # 1. Try browser Geolocation API (requires user permission)
    try:
        gps_location = await get_browser_gps()  # Street-level
        return UserLocation(
            city=gps_location.city,
            latitude=gps_location.lat,
            longitude=gps_location.lon,
            accuracy_note="GPS (±10m)"
        )
    except:
        pass
    
    # 2. Fallback to IP geolocation
    ip_location = await detect_user_location_from_ip()
    return UserLocation(
        ...ip_location...,
        accuracy_note="IP-based (±50km)"
    )
```

---

## Integration with Existing Chronos Features

### 1. Sanity Check (Stage 2)

Geolocation doesn't change sanity check logic:
```python
# Same as v2.0 - checks terrain match
feasibility = check_activity_feasibility(
    activity="beach day",
    location=location  # Still validated the same way
)
```

### 2. Weather Handling (Stage 3)

Weather data includes travel implications:
```python
# LLM gets enriched weather context:
context = {
    "weather": {
        "human_summary": "Sunny, 28°C...",
        "travel_note": "Good conditions for 6-hour flight",  # NEW
    },
    "travel_info": {
        "duration_hours": 0,
        "mode": "flight"
    }
}
```

### 3. LLM Planning (Stage 7)

Enhanced prompt includes travel time:
```python
prompt = """
DESTINATION: Goa, India
TRAVEL: From Nadiād (820km, ~0 hour flight)
NEARBY PLACES: [Coastal Kitchen, Beach Shack Cafe, ...]
WEATHER: Sunny, 28°C

Plan the day accounting for:
1. Travel time from user's location
2. Nearby attractions at destination
3. Group activities by proximity
"""
```

---

## Testing

### Run Geolocation Tests

```bash
# Test complete pipeline with geolocation
python integration_with_geolocation_example.py

# Test individual modules
python -c "
import asyncio
from user_location import detect_user_location

async def test():
    loc = await detect_user_location()
    print(f'You are in {loc.city}, {loc.country}')

asyncio.run(test())
"
```

### Expected Output

```
🌍 CHRONOS WITH GOOGLE MAPS INTEGRATION
✅ Pipeline validation passed!
📍 Your Current Location: Nadiād, India
✈️ Travel Information: 820.1 km, ~0 hours flight
🏪 Nearby Places: [Coastal Kitchen, Beach Shack Cafe, ...]
📅 COMPLETE DAY PLAN: 5 steps with times and locations
✅ SUCCESS
```

---

## Performance Considerations

| Operation | Time | Cost | Notes |
|-----------|------|------|-------|
| Location validation | <10ms | Free | Local DB lookup |
| Sanity check | <5ms | Free | Rule matching |
| Weather fetch | 100-500ms | Free | Mock or API |
| **Geolocation (IP)** | 50-200ms | Free | ip-api.com |
| **Distance Matrix** | 100-300ms | 0.005$/req | Google Maps |
| **Places search** | 200-500ms | 0.032$/req | Google Maps |
| **Total pipeline** | 500-1500ms | <0.04$ | One complete plan |

---

## FAQ

**Q: How accurate is IP geolocation?**
A: City-level (~50km radius). For street-level, add browser GPS.

**Q: What if the user is offline?**
A: Geolocation fails gracefully; uses fallback location (Delhi) or lets user specify.

**Q: Can I use a different maps provider?**
A: Yes. Replace GoogleMapsClient with OpenStreetMap, MapBox, or local DBs.

**Q: Does this cost money?**
A: Free with mock API (built-in). Real Google Maps charges per request (~$0.04-0.05/usage).

**Q: How do I disable geolocation?**
A: Edit pipeline.py, skip STAGE 4-5, use original 4-stage pipeline.

---

## Next Steps

1. ✅ **v2.1 Delivered:** IP geolocation + Google Maps integration
2. 📋 **v2.2 (Optional):** Browser GPS for higher accuracy
3. 📋 **v2.3 (Optional):** Multi-day trip planning with hotels/transport
4. 📋 **v2.4 (Optional):** Real-time traffic + opening hours optimization

---

## Files Modified/Created in v2.1

```
NEW FILES:
  ✓ user_location.py (180 lines) - Geolocation detection
  ✓ google_maps_integration.py (380 lines) - Maps API wrapper
  ✓ integration_with_geolocation_example.py (450 lines) - Full example
  ✓ GEOLOCATION_GUIDE.md (this file)

MODIFIED FILES:
  ✓ pipeline.py - Added stages 4-5, extended PipelineResult
  ✓ (Your existing files: geocoding.py, sanity_check.py, etc. unchanged)

UNCHANGED FILES:
  geocoding.py, sanity_check.py, weather_api.py, planner_agent.py,
  models.py, tools.py, utils.py, etc.
```

---

## Support

For issues or questions:
- Check [QUICK_START.md](QUICK_START.md) for common setup issues
- See [ARCHITECTURE_GUIDE.md](ARCHITECTURE_GUIDE.md) for technical details
- Review [test_guardrails.py](test_guardrails.py) for usage examples
