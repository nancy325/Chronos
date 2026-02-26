"""
weather_advice.py - Weather-to-Advice Translation (Human-Friendly Interpretations)

Converts raw weather metrics into relatable, actionable advice that users can easily
understand and act upon. Never outputs technical numbers - always translates to
comfort, clothing, and preparation recommendations.
"""

from models import WeatherCondition


def get_temperature_advice(temp_celsius: float) -> str:
    """Convert temperature to practical clothing/comfort advice."""
    if temp_celsius <= 0:
        return "Bundle up in warm layers - it's freezing out there"
    elif temp_celsius <= 5:
        return "You'll need a heavy coat and warm layers"
    elif temp_celsius <= 10:
        return "Wear a warm jacket and maybe a scarf"
    elif temp_celsius <= 15:
        return "A light jacket or sweater will keep you comfortable"
    elif temp_celsius <= 20:
        return "Perfect for a light long-sleeve or thin jacket"
    elif temp_celsius <= 25:
        return "You'll feel great in a t-shirt or light top"
    elif temp_celsius <= 30:
        return "Shorts and a t-shirt weather - very comfortable"
    elif temp_celsius <= 35:
        return "Stay cool with light, breathable clothing"
    else:
        return "Dress light and stay hydrated - it's quite hot"


def get_wind_advice(wind_speed_kmh: float) -> str:
    """Convert wind speed to practical comfort advice."""
    if wind_speed_kmh <= 5:
        return "Barely a breeze - very calm conditions"
    elif wind_speed_kmh <= 15:
        return "A gentle breeze that feels refreshing"
    elif wind_speed_kmh <= 25:
        return "Quite breezy - you might want to tie your hair back"
    elif wind_speed_kmh <= 40:
        return "Pretty windy - hold onto hats and light items"
    else:
        return "Very strong winds - be extra careful with loose items"


def get_precipitation_advice(precipitation_chance: int) -> str:
    """Convert precipitation chance to practical preparation advice."""
    if precipitation_chance <= 10:
        return "No need to worry about rain"
    elif precipitation_chance <= 30:
        return "Might want to bring a light jacket just in case"
    elif precipitation_chance <= 50:
        return "Consider bringing a small umbrella or rain jacket"
    elif precipitation_chance <= 70:
        return "Definitely pack an umbrella - rain is likely"
    else:
        return "Expect rain - bring proper rain gear"


def get_humidity_comfort_advice(humidity_percent: int, temp_celsius: float) -> str:
    """Convert humidity and temperature to comfort advice."""
    if temp_celsius > 25 and humidity_percent > 70:
        return "It'll feel quite muggy - stay hydrated and take breaks in shade"
    elif temp_celsius > 20 and humidity_percent > 80:
        return "The air will feel a bit sticky and warm"
    elif humidity_percent < 30:
        return "The air will feel quite dry - consider lip balm or moisturizer"
    elif humidity_percent > 85:
        return "It'll feel pretty humid - you might get warm quickly"
    else:
        return "Humidity levels should feel comfortable"


def get_overall_weather_advice(weather: WeatherCondition) -> str:
    """Create comprehensive human-friendly weather advice."""
    advice_parts = []
    
    # Temperature advice
    temp_advice = get_temperature_advice(weather.temperature_celsius)
    advice_parts.append(temp_advice)
    
    # Wind advice (only if significant)
    if weather.wind_speed_kmh > 15:
        wind_advice = get_wind_advice(weather.wind_speed_kmh)
        advice_parts.append(wind_advice)
    
    # Precipitation advice (only if chance exists)
    if weather.precipitation_chance > 10:
        rain_advice = get_precipitation_advice(weather.precipitation_chance)
        advice_parts.append(rain_advice)
    
    # Humidity comfort (only if extreme)
    if (weather.humidity_percent > 80) or (weather.humidity_percent < 30):
        humidity_advice = get_humidity_comfort_advice(weather.humidity_percent, weather.temperature_celsius)
        advice_parts.append(humidity_advice)
    
    return " | ".join(advice_parts)


def get_activity_specific_advice(weather: WeatherCondition, activity_type: str) -> str:
    """Get weather advice tailored to specific activity types."""
    base_advice = get_overall_weather_advice(weather)
    
    # Add activity-specific recommendations
    activity_tips = []
    
    if "beach" in activity_type.lower() or "swimming" in activity_type.lower():
        if weather.temperature_celsius < 20:
            activity_tips.append("Water might feel chilly - consider a wetsuit")
        if weather.wind_speed_kmh > 20:
            activity_tips.append("Waves might be choppy due to wind")
    
    elif "hiking" in activity_type.lower() or "walking" in activity_type.lower():
        if weather.temperature_celsius > 28:
            activity_tips.append("Start early to avoid peak heat")
        if weather.precipitation_chance > 30:
            activity_tips.append("Trails might be slippery - wear good shoes")
    
    elif "picnic" in activity_type.lower() or "outdoor" in activity_type.lower():
        if weather.wind_speed_kmh > 15:
            activity_tips.append("Bring clips or weights for tablecloth and napkins")
        if weather.precipitation_chance > 20:
            activity_tips.append("Have an indoor backup plan ready")
    
    elif "cycling" in activity_type.lower() or "bike" in activity_type.lower():
        if weather.wind_speed_kmh > 25:
            activity_tips.append("Expect headwinds - might take longer than usual")
        if weather.temperature_celsius > 30:
            activity_tips.append("Take frequent breaks and bring extra water")
    
    if activity_tips:
        return f"{base_advice} | Activity tips: {' | '.join(activity_tips)}"
    
    return base_advice