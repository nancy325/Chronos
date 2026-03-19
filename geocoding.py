"""
geocoding.py - Location validation and geocoding module.

Strict location validation is the FIRST guardrail.
If a location doesn't exist or can't be geocoded, fail fast.

Provides:
- Location validation against known databases
- Geocoding (location → lat/lon)
- Location metadata (country, continent, terrain type)
"""

from dataclasses import dataclass
from typing import Optional
import os
import time
import difflib
import httpx


@dataclass
class Location:
    """Geocoded location with metadata."""
    name: str                    # User-friendly name (e.g., "Anand, Gujarat, India")
    latitude: float
    longitude: float
    country: str
    state_or_region: str
    continent: str
    terrain_type: str            # "coastal", "desert", "mountain", "plain", "urban", "forest"
    is_valid: bool = True


# ──────────────────────────────────────────────────────────────────────────────
# Mock Geocoding Database
# These are hardcoded for demo; replace with real API calls
# ──────────────────────────────────────────────────────────────────────────────

MOCK_LOCATION_DATABASE = {
    # India
    ("anand", "india"): Location(
        name="Anand, Gujarat, India",
        latitude=22.5585, longitude=72.9297,
        country="India", state_or_region="Gujarat",
        continent="Asia", terrain_type="plain"
    ),
    ("mumbai", "india"): Location(
        name="Mumbai, Maharashtra, India",
        latitude=19.0760, longitude=72.8777,
        country="India", state_or_region="Maharashtra",
        continent="Asia", terrain_type="coastal"
    ),
    ("goa", "india"): Location(
        name="Goa, India",
        latitude=15.3667, longitude=73.8333,
        country="India", state_or_region="Goa",
        continent="Asia", terrain_type="coastal"
    ),
    ("delhi", "india"): Location(
        name="Delhi, India",
        latitude=28.7041, longitude=77.1025,
        country="India", state_or_region="Delhi",
        continent="Asia", terrain_type="urban"
    ),
    ("bangalore", "india"): Location(
        name="Bangalore, Karnataka, India",
        latitude=12.9716, longitude=77.5946,
        country="India", state_or_region="Karnataka",
        continent="Asia", terrain_type="urban"
    ),
    ("jaipur", "india"): Location(
        name="Jaipur, Rajasthan, India",
        latitude=26.9124, longitude=75.7873,
        country="India", state_or_region="Rajasthan",
        continent="Asia", terrain_type="desert"
    ),
    
    # USA
    ("new york", "usa"): Location(
        name="New York, NY, USA",
        latitude=40.7128, longitude=-74.0060,
        country="USA", state_or_region="New York",
        continent="North America", terrain_type="urban coastal"
    ),
    ("los angeles", "usa"): Location(
        name="Los Angeles, CA, USA",
        latitude=34.0522, longitude=-118.2437,
        country="USA", state_or_region="California",
        continent="North America", terrain_type="urban coastal"
    ),
    ("denver", "usa"): Location(
        name="Denver, CO, USA",
        latitude=39.7392, longitude=-104.9903,
        country="USA", state_or_region="Colorado",
        continent="North America", terrain_type="mountain"
    ),
    ("vegas", "usa"): Location(
        name="Las Vegas, NV, USA",
        latitude=36.1699, longitude=-115.1398,
        country="USA", state_or_region="Nevada",
        continent="North America", terrain_type="desert"
    ),
    
    # Europe
    ("paris", "france"): Location(
        name="Paris, France",
        latitude=48.8566, longitude=2.3522,
        country="France", state_or_region="Île-de-France",
        continent="Europe", terrain_type="urban"
    ),
    ("london", "uk"): Location(
        name="London, UK",
        latitude=51.5074, longitude=-0.1278,
        country="UK", state_or_region="England",
        continent="Europe", terrain_type="urban"
    ),
    ("swiss alps", "switzerland"): Location(
        name="Swiss Alps, Switzerland",
        latitude=46.5197, longitude=8.2275,
        country="Switzerland", state_or_region="Central Switzerland",
        continent="Europe", terrain_type="mountain"
    ),
}


NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_TIMEOUT_SECONDS = 5.0
NOMINATIM_MIN_SECONDS_BETWEEN_REQUESTS = 1.0
DEFAULT_GEOCODER_USER_AGENT = os.getenv(
    "CHRONOS_GEOCODER_USER_AGENT",
    "Chronos/2.1 (OpenStreetMap Nominatim geocoder; contact: admin@example.com)",
)
GEOCODER_CONTACT_EMAIL = os.getenv("CHRONOS_GEOCODER_EMAIL", "")
_LAST_NOMINATIM_REQUEST_TS = 0.0


def _respect_nominatim_rate_limit() -> None:
    """Keep requests at or below 1 req/sec for the public Nominatim endpoint."""
    global _LAST_NOMINATIM_REQUEST_TS
    now = time.time()
    elapsed = now - _LAST_NOMINATIM_REQUEST_TS
    if elapsed < NOMINATIM_MIN_SECONDS_BETWEEN_REQUESTS:
        time.sleep(NOMINATIM_MIN_SECONDS_BETWEEN_REQUESTS - elapsed)
    _LAST_NOMINATIM_REQUEST_TS = time.time()


def geocode_location(city: str, state_or_country: Optional[str] = None) -> Optional[Location]:
    """
    Geocode a user-provided location string.
    
    RETURNS: Location object if found, None if not found.
    
    This is the FIRST guardrail — if location can't be found, stop immediately.
    
    Args:
        city: City or location name
        state_or_country: Optional state/region/country clarification
        
    Returns:
        Location object if valid, None otherwise
        
    Note:
        This function first checks the local mock database (deterministic tests)
        and then falls back to OpenStreetMap Nominatim for real geocoding.
    """
    city_clean = city.lower().strip()
    region_clean = (state_or_country or "").lower().strip()
    query_key = (city_clean, region_clean)
    
    # Try exact match first
    if query_key in MOCK_LOCATION_DATABASE:
        return MOCK_LOCATION_DATABASE[query_key]
    
    # Try fuzzy match (city only, ignoring state/country)
    city_key = city_clean
    for (db_city, db_region), location in MOCK_LOCATION_DATABASE.items():
        if db_city == city_key:
            return location

    # Fall back to real geocoding via OpenStreetMap Nominatim
    return _geocode_with_nominatim(city_clean, region_clean)


def _geocode_with_nominatim(city: str, state_or_country: str) -> Optional[Location]:
    """Geocode using OpenStreetMap Nominatim Search API."""
    if not city:
        return None

    query = ", ".join(part for part in [city, state_or_country] if part).strip()
    if not query:
        return None

    params = {
        "q": query,
        "format": "jsonv2",
        "limit": 1,
        "addressdetails": 1,
    }
    if GEOCODER_CONTACT_EMAIL:
        params["email"] = GEOCODER_CONTACT_EMAIL
    headers = {
        "User-Agent": DEFAULT_GEOCODER_USER_AGENT,
        "Accept": "application/json",
    }

    try:
        _respect_nominatim_rate_limit()
        with httpx.Client(timeout=NOMINATIM_TIMEOUT_SECONDS) as client:
            response = client.get(NOMINATIM_SEARCH_URL, params=params, headers=headers)

        if response.status_code != 200:
            return None

        payload = response.json()
        if not isinstance(payload, list) or not payload:
            return None

        top = payload[0]
        address = top.get("address", {}) if isinstance(top, dict) else {}

        location_name = top.get("display_name") or query.title()
        country = address.get("country") or state_or_country.title() or "Unknown"
        state = (
            address.get("state")
            or address.get("region")
            or address.get("county")
            or state_or_country.title()
            or "Unknown"
        )
        continent = _infer_continent(country)
        terrain_type = _infer_terrain_type(top)

        return Location(
            name=location_name,
            latitude=float(top.get("lat", 0.0)),
            longitude=float(top.get("lon", 0.0)),
            country=country,
            state_or_region=state,
            continent=continent,
            terrain_type=terrain_type,
        )
    except Exception:
        # Network/API/parsing failures should not break planning pipeline.
        return None
    
    # Location not found
    return None


def validate_location(city: str, state_or_country: Optional[str] = None) -> tuple[bool, Optional[Location], str]:
    """
    Validate a location for existence and accessibility.
    
    RETURNS: (is_valid, Location, error_message)
    
    This is the fail-fast guardrail. If invalid, return error immediately.
    
    Args:
        city: City or location name
        state_or_country: Optional state/region clarification
        
    Returns:
        Tuple of (valid, Location or None, error message)
    """
    if not city or not city.strip():
        return False, None, "Location name cannot be empty."
    
    location = geocode_location(city, state_or_country)
    
    if not location:
        suggestions = _get_location_suggestions(city, state_or_country)
        suggestion_text = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        error_msg = f"Location '{city}' not found in database.{suggestion_text}"
        return False, None, error_msg
    
    return True, location, ""


def _get_location_suggestions(
    partial_city: str,
    state_or_country: Optional[str] = None,
    max_suggestions: int = 3,
) -> list[str]:
    """
    Get suggestions for misspelled/ambiguous locations.

    Strategy:
    1) Prefix/substring suggestions from local mock DB
    2) If insufficient, ask Nominatim for top matches near the query string
    """
    partial = partial_city.lower().strip()
    matches: list[str] = []
    
    for (db_city, _), location in MOCK_LOCATION_DATABASE.items():
        if partial in db_city or db_city.startswith(partial):
            matches.append(location.name)

    # Add fuzzy nearest matches for misspellings (e.g., "Anad" -> "Anand")
    db_city_names = [db_city for (db_city, _) in MOCK_LOCATION_DATABASE.keys()]
    close_city_matches = difflib.get_close_matches(partial, db_city_names, n=max_suggestions, cutoff=0.6)
    for city_name in close_city_matches:
        for (db_city, _), location in MOCK_LOCATION_DATABASE.items():
            if db_city == city_name and location.name not in matches:
                matches.append(location.name)
    
    if len(matches) >= max_suggestions:
        return matches[:max_suggestions]

    osm_matches = _suggest_with_nominatim(partial_city, state_or_country, max_suggestions=max_suggestions)
    deduped = []
    for suggestion in [*matches, *osm_matches]:
        if suggestion not in deduped:
            deduped.append(suggestion)

    return deduped[:max_suggestions]


def _suggest_with_nominatim(
    city: str,
    state_or_country: Optional[str] = None,
    max_suggestions: int = 3,
) -> list[str]:
    """Return nearest/most relevant valid places from Nominatim."""
    city_clean = city.strip()
    region_clean = (state_or_country or "").strip()
    if not city_clean:
        return []

    query = ", ".join(part for part in [city_clean, region_clean] if part).strip()
    params = {
        "q": query,
        "format": "jsonv2",
        "limit": min(max_suggestions, 5),
        "addressdetails": 0,
    }
    if GEOCODER_CONTACT_EMAIL:
        params["email"] = GEOCODER_CONTACT_EMAIL
    headers = {
        "User-Agent": DEFAULT_GEOCODER_USER_AGENT,
        "Accept": "application/json",
    }

    try:
        _respect_nominatim_rate_limit()
        with httpx.Client(timeout=NOMINATIM_TIMEOUT_SECONDS) as client:
            response = client.get(NOMINATIM_SEARCH_URL, params=params, headers=headers)
        if response.status_code != 200:
            return []

        payload = response.json()
        if not isinstance(payload, list):
            return []

        suggestions = []
        for item in payload:
            display_name = item.get("display_name") if isinstance(item, dict) else None
            lat = item.get("lat") if isinstance(item, dict) else None
            lon = item.get("lon") if isinstance(item, dict) else None
            if display_name and lat is not None and lon is not None:
                suggestions.append(f"{display_name} ({lat}, {lon})")

        return suggestions[:max_suggestions]
    except Exception:
        return []


def _infer_terrain_type(nominatim_item: dict) -> str:
    """Best-effort terrain classification from Nominatim class/type."""
    category = str(nominatim_item.get("category", "")).lower()
    place_type = str(nominatim_item.get("type", "")).lower()
    label = f"{category} {place_type}"

    if any(token in label for token in ["beach", "coast", "bay", "sea"]):
        return "coastal"
    if any(token in label for token in ["mountain", "peak", "ridge", "alpine"]):
        return "mountain"
    if any(token in label for token in ["desert", "dune"]):
        return "desert"
    if any(token in label for token in ["forest", "wood"]):
        return "forest"
    return "urban"


def _infer_continent(country: str) -> str:
    """Best-effort continent mapping for commonly used countries."""
    key = country.strip().lower()
    continent_map = {
        "india": "Asia",
        "usa": "North America",
        "united states": "North America",
        "france": "Europe",
        "uk": "Europe",
        "united kingdom": "Europe",
        "switzerland": "Europe",
        "germany": "Europe",
        "italy": "Europe",
        "spain": "Europe",
        "canada": "North America",
        "australia": "Oceania",
        "japan": "Asia",
        "brazil": "South America",
    }
    return continent_map.get(key, "Unknown")


def get_location_metadata(location: Location) -> dict:
    """
    Return enriched location metadata for sanity checks.
    
    This data drives the geographic feasibility logic.
    """
    return {
        "name": location.name,
        "latitude": location.latitude,
        "longitude": location.longitude,
        "country": location.country,
        "state": location.state_or_region,
        "continent": location.continent,
        "terrain_type": location.terrain_type,
        "is_coastal": "coastal" in location.terrain_type.lower(),
        "is_mountain": "mountain" in location.terrain_type.lower(),
        "is_desert": "desert" in location.terrain_type.lower(),
        "is_urban": "urban" in location.terrain_type.lower(),
    }
