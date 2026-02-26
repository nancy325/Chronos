#!/usr/bin/env python3
"""
Test script to verify the new human-friendly weather features in Chronos.
This script demonstrates the enhanced functionality that translates raw weather 
metrics into practical, relatable advice.
"""

import asyncio
from models import WeatherCondition
from utils import (
    get_overall_weather_advice,
    get_temperature_advice,
    get_wind_advice,
    get_precipitation_advice,
    sanitize_user_input,
    format_weather_summary,
    format_risk_explanation
)
from tools import generate_simulated_weather


def test_weather_advice_generation():
    """Test the new human-friendly weather advice functions."""
    print("🧪 Testing Weather Advice Generation")
    print("=" * 50)
    
    # Create a test weather condition
    test_weather = WeatherCondition(
        temperature_celsius=22.0,
        condition="partly cloudy",
        precipitation_chance=30,
        wind_speed_kmh=18.0,
        humidity_percent=65,
        forecast_date="2026-02-27",
        location="Test City",
        is_simulated=True
    )
    
    print("📊 Raw Weather Data:")
    print(f"  Temperature: {test_weather.temperature_celsius}°C")
    print(f"  Condition: {test_weather.condition}")
    print(f"  Precipitation: {test_weather.precipitation_chance}%")
    print(f"  Wind: {test_weather.wind_speed_kmh} km/h")
    print(f"  Humidity: {test_weather.humidity_percent}%")
    
    print("\n💡 Human-Friendly Advice:")
    print("  Temperature:", get_temperature_advice(test_weather.temperature_celsius))
    print("  Wind:", get_wind_advice(test_weather.wind_speed_kmh))
    print("  Rain:", get_precipitation_advice(test_weather.precipitation_chance))
    
    print("\n🎯 Complete Advisory:", get_overall_weather_advice(test_weather))
    print("\n" + "=" * 50)


def test_input_sanitization():
    """Test the input sanitization functionality."""
    print("\n🧹 Testing Input Sanitization")
    print("=" * 50)
    
    test_inputs = [
        "Plan a beach picnic in Miami tomorrow morning",
        "I want to go hiking and camping this weekend",
        "Movie night at home with friends",
        "Outdoor wedding ceremony in the garden"
    ]
    
    for user_input in test_inputs:
        print(f"\n📝 Input: '{user_input}'")
        sanitized = sanitize_user_input(user_input)
        print(f"  🎯 Activities: {sanitized['activities']}")
        print(f"  ⏰ Time indicators: {sanitized['time_indicators']}")
        print(f"  🌤️ Weather sensitivity: {sanitized['weather_sensitivity']}")


def test_simulated_weather_with_advice():
    """Test the enhanced simulated weather generation with human-friendly summaries."""
    print("\n🌤️ Testing Enhanced Simulated Weather")
    print("=" * 50)
    
    locations = ["Miami, Florida", "Denver, Colorado", "Seattle, Washington"]
    
    for location in locations:
        print(f"\n📍 {location}:")
        weather = generate_simulated_weather(location, "2026-02-28")
        print(f"  Condition: {weather.condition}")
        print(f"  🎯 Practical advice: {weather.human_friendly_summary}")


async def test_weather_formatting():
    """Test the updated weather formatting functions."""
    print("\n📊 Testing Weather Formatting")
    print("=" * 50)
    
    # Create different weather scenarios
    scenarios = [
        {"temp": 5, "condition": "light snow", "precip": 60, "wind": 25, "humidity": 80},
        {"temp": 28, "condition": "sunny", "precip": 5, "wind": 8, "humidity": 45},
        {"temp": 18, "condition": "rainy", "precip": 85, "wind": 30, "humidity": 90},
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n🌦️ Scenario {i}:")
        weather = WeatherCondition(
            temperature_celsius=scenario["temp"],
            condition=scenario["condition"],
            precipitation_chance=scenario["precip"],
            wind_speed_kmh=scenario["wind"],
            humidity_percent=scenario["humidity"],
            forecast_date="2026-02-28",
            location="Test Location"
        )
        weather.human_friendly_summary = get_overall_weather_advice(weather)
        
        print(f"  Summary: {format_weather_summary(weather)}")
        
        from utils import calculate_weather_risk
        risk = calculate_weather_risk(weather)
        print(f"  Risk explanation: {format_risk_explanation(risk, weather)}")


def main():
    """Run all tests to verify new functionality."""
    print("🚀 Chronos Enhanced Weather Features Test")
    print("Testing the new practical, human-friendly weather approach\n")
    
    test_weather_advice_generation()
    test_input_sanitization()
    test_simulated_weather_with_advice()
    
    # Run async test
    asyncio.run(test_weather_formatting())
    
    print("\n✅ All tests completed!")
    print("\n📋 Summary of New Features:")
    print("  • Weather metrics translated to practical advice")
    print("  • Input sanitization for better API processing")
    print("  • Human-friendly weather summaries")
    print("  • Relatable risk explanations")
    print("  • Enhanced UI with actionable weather guidance")


if __name__ == "__main__":
    main()