"""
weather_api.py - Weather data module with mock API.

Provides:
- Mock weather fetching (replace with real API)
- Weather data caching
- Graceful fallbacks
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import random


@dataclass
class WeatherData:
    """Weather observation or forecast."""
    temperature_celsius: float
    condition: str
    precipitation_chance: int  # 0-100
    wind_speed_kmh: float
    humidity_percent: int      # 0-100
    uv_index: float
    forecast_date: str          # YYYY-MM-DD
    location_name: str


# ──────────────────────────────────────────────────────────────────────────────
# Mock Weather Database
# Replace with real API: OpenWeatherMap, WeatherAPI, wttr.in, etc.
# ──────────────────────────────────────────────────────────────────────────────

MOCK_WEATHER_DATABASE = {
    # location, date -> WeatherData
    ("anand, gujarat, india", "2026-03-16"): WeatherData(
        temperature_celsius=32.1,
        condition="sunny",
        precipitation_chance=5,
        wind_speed_kmh=12.0,
        humidity_percent=55,
        uv_index=7.2,
        forecast_date="2026-03-16",
        location_name="Anand, Gujarat, India"
    ),
    ("mumbai, maharashtra, india", "2026-03-16"): WeatherData(
        temperature_celsius=31.5,
        condition="partly cloudy",
        precipitation_chance=10,
        wind_speed_kmh=15.0,
        humidity_percent=72,
        uv_index=7.5,
        forecast_date="2026-03-16",
        location_name="Mumbai, Maharashtra, India"
    ),
    ("goa, india", "2026-03-16"): WeatherData(
        temperature_celsius=30.8,
        condition="sunny",
        precipitation_chance=5,
        wind_speed_kmh=18.0,
        humidity_percent=68,
        uv_index=7.8,
        forecast_date="2026-03-16",
        location_name="Goa, India"
    ),
}


def fetch_weather(location_name: str, latitude: float, longitude: float, 
                  forecast_date: str) -> Optional[WeatherData]:
    """
    Fetch weather data for a location and date.
    
    RETURNS: WeatherData if available, None if not cached or API fails.
    
    Args:
        location_name: Human-readable location name
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        forecast_date: Date in YYYY-MM-DD format
        
    Returns:
        WeatherData object or None
        
    TODO: Replace with real API call:
        - OpenWeatherMap: https://openweathermap.org/api
        - WeatherAPI: https://www.weatherapi.com/
        - wttr.in: https://wttr.in/
        
    Example (using OpenWeatherMap):
        import httpx
        api_key = os.getenv("OPENWEATHER_API_KEY")
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat={latitude}&lon={longitude}&appid={api_key}&units=metric"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            data = response.json()
            return parse_weather_response(data, forecast_date)
    """
    cache_key = (location_name.lower(), forecast_date)
    
    # Check mock database
    if cache_key in MOCK_WEATHER_DATABASE:
        return MOCK_WEATHER_DATABASE[cache_key]
    
    # Not found in mock database
    # In real implementation, would call actual API here
    # For now, return None (caller will handle missing data gracefully)
    return None


def generate_simulated_weather(location_name: str, latitude: float, longitude: float,
                               forecast_date: str) -> WeatherData:
    """
    Generate realistic simulated weather for demos.
    Deterministic based on location + date so results are reproducible.
    
    Args:
        location_name: Human-readable location name
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        forecast_date: Date in YYYY-MM-DD format
        
    Returns:
        WeatherData with simulated values
    """
    # Seed randomness based on location + date for reproducibility
    seed_value = hash(f"{location_name.lower()}_{forecast_date}") % 10000
    random.seed(seed_value)
    
    # Latitude-based temperature baseline (equator is hotter)
    base_temp = 35 - (abs(latitude) * 0.3)
    
    conditions_list = ["sunny", "partly cloudy", "cloudy", "light rain", "rainy"]
    condition = random.choice(conditions_list)
    
    # Adjust temp based on condition
    temp = base_temp + random.uniform(-5, 5)
    if "rain" in condition:
        temp -= random.uniform(2, 4)
    
    precip_map = {
        "sunny": random.randint(0, 10),
        "partly cloudy": random.randint(10, 30),
        "cloudy": random.randint(20, 50),
        "light rain": random.randint(40, 70),
        "rainy": random.randint(70, 100),
    }
    
    return WeatherData(
        temperature_celsius=round(temp, 1),
        condition=condition,
        precipitation_chance=precip_map[condition],
        wind_speed_kmh=round(random.uniform(5, 25), 1),
        humidity_percent=random.randint(40, 85),
        uv_index=round(random.uniform(2, 10), 1),
        forecast_date=forecast_date,
        location_name=location_name
    )


def get_weather_summary(weather: WeatherData) -> str:
    """
    Translate raw weather metrics into human-friendly advice.
    
    NO raw metrics. Only actionable advice about:
    - Clothing choices
    - Comfort considerations
    - Activity adjustments
    """
    temp = weather.temperature_celsius
    condition = weather.condition
    humidity = weather.humidity_percent
    wind = weather.wind_speed_kmh
    
    advice_pieces = []
    
    # Temperature advice
    if temp < 10:
        advice_pieces.append("You'll need a warm jacket and layers")
    elif temp < 15:
        advice_pieces.append("Bring a light jacket")
    elif temp < 20:
        advice_pieces.append("A light sweater or long sleeves would be comfortable")
    elif temp < 25:
        advice_pieces.append("Perfect t-shirt weather")
    elif temp < 30:
        advice_pieces.append("You'll feel warm in light clothing")
    else:
        advice_pieces.append("It'll be quite hot—wear light, breathable clothes and stay hydrated")
    
    # Condition-specific advice
    if condition == "sunny":
        advice_pieces.append("Sunscreen and sunglasses are a must")
    elif condition == "partly cloudy":
        advice_pieces.append("Some sun, some shade—still wear sunscreen")
    elif "rain" in condition:
        advice_pieces.append("Bring an umbrella or rain jacket")
    
    # Wind advice
    if wind > 20:
        advice_pieces.append("It'll be breezy—tie your hair back if needed")
    
    # Humidity advice
    if humidity > 75:
        advice_pieces.append("High humidity—you might feel sticky, so dress in breathable fabrics")
    
    return " ".join(advice_pieces)
