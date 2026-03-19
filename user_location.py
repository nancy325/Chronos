"""
user_location.py - Detect user's current location via IP geolocation.

PROVIDES:
- IP-based geolocation (quick, usually accurate to city level)
- User's home location + coordinates
- Used to estimate travel time to destination

LIMITATIONS:
- IP geolocation is accurate to city level, not street level
- VPN/Proxy will give inaccurate results
- For production: Supplement with browser Geolocation API (GPS-level accuracy)
"""

from dataclasses import dataclass
from typing import Optional
import httpx


@dataclass
class UserLocation:
    """User's detected location."""
    city: str
    country: str
    latitude: float
    longitude: float
    timezone: Optional[str] = None
    isp: Optional[str] = None
    accuracy_note: str = "IP-based geolocation (city-level accuracy)"


async def detect_user_location_from_ip() -> Optional[UserLocation]:
    """
    Detect user's location from IP address using free IP geolocation API.
    
    Uses ip-api.com (free tier: 45 requests/minute)
    For production: Use a paid service or combine with browser GPS
    
    RETURNS: UserLocation if detected, None if API fails
    
    Note: This is server-side detection of client IP
    For client-side GPS accuracy, use browser Geolocation API instead:
        navigator.geolocation.getCurrentPosition(...)
    """
    try:
        # Use ip-api.com free tier (no key required)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "http://ip-api.com/json/?fields=status,city,country,lat,lon,timezone,isp",
                timeout=5.0
            )
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        
        if data.get("status") != "success":
            return None
        
        return UserLocation(
            city=data.get("city", "Unknown"),
            country=data.get("country", "Unknown"),
            latitude=float(data.get("lat", 0)),
            longitude=float(data.get("lon", 0)),
            timezone=data.get("timezone"),
            isp=data.get("isp"),
        )
    
    except Exception as e:
        print(f"⚠️ Geolocation detection failed: {e}")
        return None


def get_hardcoded_user_location_for_demo() -> UserLocation:
    """
    Hardcoded user location for demo/testing.
    Replace with real geolocation in production.
    """
    return UserLocation(
        city="Delhi",
        country="India",
        latitude=28.7041,
        longitude=77.1025,
        timezone="IST",
        accuracy_note="Demo location (hardcoded)"
    )


async def detect_user_location(use_ip_geolocation: bool = True) -> UserLocation:
    """
    Detect user's current location.
    
    For development/demos: use hardcoded location
    For production: detect from IP or browser GPS
    
    Args:
        use_ip_geolocation: If True, try IP-based detection
        
    Returns:
        UserLocation with city, country, coordinates
    """
    if use_ip_geolocation:
        location = await detect_user_location_from_ip()
        if location:
            return location
    
    # Fallback to hardcoded demo location
    print("⚠️ Using demo location (Delhi). For production, implement browser GPS or use IP geolocation.")
    return get_hardcoded_user_location_for_demo()


def estimate_travel_duration_category(distance_km: float) -> str:
    """
    Categorize travel time based on distance (rough estimate).
    
    Assumes:
    - Driving: ~60 km/h average
    - Flight: ~1 hour + 3 hours connecting/boarding
    - Train: ~80 km/h average
    
    Args:
        distance_km: Distance in kilometers
        
    Returns:
        Category string: "walk", "drive_short", "drive_medium", "drive_long", "flight"
    """
    if distance_km < 1:
        return "walk"
    elif distance_km < 20:
        return "drive_short"  # < 20 min
    elif distance_km < 100:
        return "drive_medium"  # 1-2 hours
    elif distance_km < 300:
        return "drive_long"  # 3-5 hours
    else:
        return "flight"  # 4+ hours (including connections)


def get_travel_time_estimate(distance_km: float) -> dict:
    """
    Get estimated travel time (rough, for planning purposes).
    
    For accurate times, use Google Maps Distance Matrix API.
    
    Args:
        distance_km: Distance in kilometers
        
    Returns:
        Dict with time estimates for different modes
    """
    if distance_km < 1:
        return {
            "mode": "walk",
            "minutes": int(distance_km * 15),  # 15 min per km
            "description": "Walking"
        }
    elif distance_km < 20:
        return {
            "mode": "drive",
            "minutes": int(distance_km * 1),  # ~1 min per km in city
            "description": f"~{int(distance_km)} min drive"
        }
    elif distance_km < 100:
        return {
            "mode": "drive",
            "minutes": int(distance_km / 60 * 60),  # ~60 km/h
            "description": f"~{int(distance_km / 60)} hours drive"
        }
    elif distance_km < 300:
        return {
            "mode": "drive",
            "minutes": int(distance_km / 80 * 60),  # ~80 km/h
            "description": f"~{int(distance_km / 80)} hours drive"
        }
    else:
        return {
            "mode": "flight",
            "minutes": 240 + int((distance_km - 300) / 900 * 60),  # 4 hours base + flight time
            "description": f"~{int(distance_km / 900)} hours flight (+ connections)"
        }


# Example usage in docstring
"""
EXAMPLE: Detect user and estimate travel to destination

    from user_location import detect_user_location, get_travel_time_estimate
    from geocoding import validate_location
    
    # Detect where user is starting from
    user_loc = await detect_user_location(use_ip_geolocation=True)
    print(f"User is in: {user_loc.city}, {user_loc.country}")
    
    # User wants to go to Goa
    is_valid, dest_location, _ = validate_location("Goa", "India")
    
    # Calculate distance and travel time
    import math
    dist = math.sqrt(
        (user_loc.latitude - dest_location.latitude)**2 + 
        (user_loc.longitude - dest_location.longitude)**2
    ) * 111  # Rough conversion to km
    
    travel = get_travel_time_estimate(dist)
    print(f"Travel to Goa: {travel['description']}")
    
    # Now plan the day at destination (Goa)
    # Groups nearby attractions based on coordinates
"""
