"""
integration_with_geolocation_example.py - Complete example with Google Maps integration.

DEMONSTRATES:
1. User location detection (IP-based geolocation)
2. Travel time estimation from user to destination
3. Finding nearby places at destination
4. Structuring day plan based on location proximity
5. Full pipeline with geolocation + LLM planning

SETUP:
1. For Google Maps API (optional, works with mock):
   - Go to: https://cloud.google.com/maps-platform
   - Enable APIs: Distance Matrix, Places, Geocoding
   - Get API key and set: GOOGLE_MAPS_API_KEY=your_key_here
   - Set up billing to avoid rate limits

2. For IP Geolocation (built-in, no setup needed):
   - Uses free ip-api.com service
   - Accurate to city level
   - For production: Add browser GPS for street-level accuracy
"""

import asyncio
import json
import os
from typing import Optional

from pipeline import run_planning_pipeline
from planner_agent import get_final_planner_prompt, PlannedOutput
from google_maps_integration import GoogleMapsClient, optimize_day_itinerary


async def plan_with_geolocation(
    activity: str,
    destination_location: str,
    forecast_date: str,
    llm_client=None,
) -> Optional[PlannedOutput]:
    """
    Full pipeline with geolocation and travel planning.
    
    NEW FEATURES:
    1. Detects user's current location (IP-based)
    2. Calculates travel time to destination
    3. Finds nearby places at destination
    4. Groups activities by proximity
    5. Structures day plan with realistic travel times
    
    Args:
        activity: User's activity (e.g., "beach day with dining")
        destination_location: Where they want to go (e.g., "Goa, India")
        forecast_date: Date for planning (YYYY-MM-DD)
        llm_client: Your LLM client (optional)
        
    Returns:
        PlannedOutput with structured plan
    """
    
    print("\n" + "="*70)
    print("CHRONOS WITH GEOLOCATION")
    print("="*70)
    
    # ──────────────────────────────────────────────────────────────
    # STAGE 1: RUN THE PIPELINE (with geolocation)
    # ──────────────────────────────────────────────────────────────
    
    print("\n📍 STAGE 1: PIPELINE VALIDATION (with Geolocation)")
    print("-" * 70)
    
    success, context, error = await run_planning_pipeline(
        activity=activity,
        location_string=destination_location,
        forecast_date=forecast_date,
        use_simulated_weather=True,
    )
    
    if not success:
        print(f"\n❌ Pipeline Error: {error.message}")
        if error.suggestion:
            print(f"   Suggestion: {error.suggestion}")
        return None
    
    # ──────────────────────────────────────────────────────────────
    # STAGE 2: DISPLAY USER & TRAVEL INFORMATION
    # ──────────────────────────────────────────────────────────────
    
    print("\n✅ Pipeline validation passed!")
    
    if context.get("user_location"):
        user_loc = context["user_location"]
        print(f"\n📍 Your Current Location:")
        print(f"   {user_loc['city']}, {user_loc['country']}")
    
    if context.get("travel_info"):
        travel = context["travel_info"]
        print(f"\n✈️ Travel Information:")
        print(f"   From: {travel.get('origin', 'Unknown')}")
        print(f"   To: {travel.get('destination', 'Unknown')}")
        print(f"   Distance: {travel.get('distance_km', 'N/A')} km")
        print(f"   Duration: {travel.get('description', 'N/A')}")
        print(f"   Mode: {travel.get('mode', 'Unknown').title()}")
    
    # ──────────────────────────────────────────────────────────────
    # STAGE 3: SHOW NEARBY PLACES AT DESTINATION
    # ──────────────────────────────────────────────────────────────
    
    if context.get("nearby_places"):
        print(f"\n🏪 Nearby Places at Destination:")
        for i, place in enumerate(context["nearby_places"][:10], 1):
            rating = f"⭐ {place['rating']}" if place.get('rating') else "⭐ N/A"
            print(f"   {i}. {place['name']} ({place['type']}) {rating}")
    
    print(f"\n📍 Location: {context['location']}")
    print(f"⚽ Activity: {context['activity']}")
    print(f"🌤️ Weather: {context['weather']['human_summary']}")
    
    # ──────────────────────────────────────────────────────────────
    # STAGE 4: GENERATE PLANNING PROMPT
    # ──────────────────────────────────────────────────────────────
    
    print("\n" + "="*70)
    print("📋 STAGE 2: GENERATE PLANNING PROMPT")
    print("="*70)
    
    # Enhanced prompt including travel information
    planning_prompt = _get_enhanced_planner_prompt(activity, context)
    print(f"\n✅ Prompt generated ({len(planning_prompt)} chars)")
    print(f"   Includes: Location, Weather, Travel Time, Nearby Places")
    
    # ──────────────────────────────────────────────────────────────
    # STAGE 5: CALL LLM
    # ──────────────────────────────────────────────────────────────
    
    print("\n" + "="*70)
    print("🤖 STAGE 3: CALL LLM FOR PLANNING")
    print("="*70)
    
    llm_response_text = await call_llm(planning_prompt, llm_client)
    
    if not llm_response_text:
        print("❌ LLM call failed")
        return None
    
    print(f"\n✅ LLM Response received ({len(llm_response_text)} chars)")
    
    # ──────────────────────────────────────────────────────────────
    # STAGE 6: PARSE AND VALIDATE OUTPUT
    # ──────────────────────────────────────────────────────────────
    
    print("\n" + "="*70)
    print("✅ STAGE 4: PARSE AND VALIDATE OUTPUT")
    print("="*70)
    
    try:
        json_str = extract_json_from_response(llm_response_text)
        response_data = json.loads(json_str)
        
        planned = PlannedOutput(**response_data)
        
        print("\n✅ Output validated against schema")
        print(f"   Activity: {planned.activity}")
        print(f"   Location: {planned.location}")
        print(f"   Feasible: {planned.feasible}")
        print(f"   Risk Level: {planned.overall_risk}")
        print(f"   Plan A Steps: {len(planned.plan_a.steps)}")
        if planned.plan_b:
            print(f"   Plan B Steps: {len(planned.plan_b.steps)}")
        
        # ──────────────────────────────────────────────────────────────
        # STAGE 7: DISPLAY FULL PLAN WITH TRAVEL TIMES
        # ──────────────────────────────────────────────────────────────
        
        print("\n" + "="*70)
        print("📅 COMPLETE DAY PLAN")
        print("="*70)
        
        print(f"\n🎯 {planned.activity.title()} at {planned.location}")
        print(f"📅 Date: {planned.date}")
        print(f"⚠️ Risk Level: {planned.overall_risk.upper()}")
        print(f"💭 {planned.weather_note}")
        
        if context.get("travel_info"):
            travel = context["travel_info"]
            print(f"\n✈️ TRAVEL TO DESTINATION")
            print(f"   {travel['description']}")
            print(f"   Depart from: {travel['origin']}")
            print(f"   Arrive at: {travel['destination']}")
        
        print(f"\n📋 PLAN A: {planned.plan_a.name}")
        print(f"   Summary: {planned.plan_a.summary}")
        print(f"   Reasoning: {planned.plan_a.reasoning}")
        print(f"\n   Steps:")
        for step in planned.plan_a.steps:
            time_str = f"{step.time_from}-{step.time_to}" if step.time_from else "Flexible"
            location_str = f" at {step.location}" if step.location else ""
            weather_flag = "🌤️ Weather-sensitive" if step.weather_sensitive else ""
            risk_note = f" [{step.risk_note}]" if step.risk_note else ""
            
            print(f"   {step.order}. {step.description}")
            print(f"      ⏰ {time_str}{location_str}")
            if weather_flag or risk_note:
                print(f"      {weather_flag}{risk_note}")
        
        if planned.plan_b:
            print(f"\n📋 PLAN B (Weather-Optimized): {planned.plan_b.name}")
            print(f"   Summary: {planned.plan_b.summary}")
            print(f"   Reasoning: {planned.plan_b.reasoning}")
            print(f"\n   Steps:")
            for step in planned.plan_b.steps:
                time_str = f"{step.time_from}-{step.time_to}" if step.time_from else "Flexible"
                print(f"   {step.order}. {step.description} ({time_str})")
        
        return planned
        
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON from LLM: {e}")
        return None
    except Exception as e:
        print(f"❌ Validation error: {e}")
        return None


def _get_enhanced_planner_prompt(activity: str, context: dict) -> str:
    """
    Enhanced planning prompt that includes:
    - Travel time from user location to destination
    - Nearby attractions (grouped by proximity)
    - Weather information
    - Activity constraints
    """
    
    travel_info = context.get("travel_info", {})
    user_location = context.get("user_location", {})
    nearby_places = context.get("nearby_places", [])
    
    nearby_places_text = ""
    if nearby_places:
        nearby_places_text = "\n\nRECOMMENDED NEARBY ATTRACTIONS:\n"
        for place in nearby_places[:10]:
            nearby_places_text += f"  - {place['name']} ({place['type']})"
            if place.get('rating'):
                nearby_places_text += f" - Rating: {place['rating']}/5"
            nearby_places_text += "\n"
    
    travel_text = ""
    if travel_info:
        travel_text = f"""
TRAVEL INFORMATION:
- Starting from: {travel_info.get('origin', 'Unknown')}
- Destination: {travel_info.get('destination', 'Unknown')}
- Distance: {travel_info.get('distance_km', 'N/A')} km
- Travel Time: {travel_info.get('description', 'N/A')}
- Mode: {travel_info.get('mode', 'Unknown').title()}

IMPORTANT: Account for travel time from {user_location.get('city', 'origin')} to {context['location']}.
If travel is long, suggest departure time accordingly.
"""
    
    prompt = f"""You are Chronos, a weather-adaptive planning assistant with geolocation awareness.

DESTINATION:
- {context['location']}
- Terrain: {context['location_metadata']['terrain_type']}

ACTIVITY REQUEST:
- {activity}

CURRENT WEATHER:
{context['weather']['human_summary']}

{travel_text}
{nearby_places_text}

YOUR TASK:
1. Confirm "{activity}" is feasible at {context['location']}
2. Create PLAN A (original as requested):
   - Account for travel time from user location
   - Use nearby attractions/restaurants from the list above
   - Group activities by proximity to minimize travel
   - 4-6 time-bounded steps with realistic durations
3. Create PLAN B (weather-optimized alternative, or null):
   - Adjust times/activities based on weather
   - Suggest alternatives at nearby venues
4. Assess overall risk: low/medium/high
5. Provide weather and logistics advice

IMPORTANT GUIDELINES:
- Add travel time at start of day (from user location if long distance)
- Group nearby activities together to minimize transit time
- Use the provided nearby attractions in your recommendations
- Ensure total day duration is realistic
- Account for breaks and meal times
- Suggest specific venues from the nearby places list when relevant
- Provide human-friendly weather advice (clothing, comfort), NOT raw metrics

RESPOND WITH ONLY valid JSON (no markdown, no extra text):
{{
  "activity": "{activity}",
  "location": "{context['location']}",
  "date": "{context['forecast_date']}",
  "feasible": true or false,
  "feasibility_note": "Why feasible or not",
  "plan_a": {{
    "name": "Plan name",
    "summary": "One-sentence summary",
    "steps": [
      {{
        "order": 1,
        "description": "Description of this step (e.g., Travel to destination, or Depart from home)",
        "time_from": "HH:MM",
        "time_to": "HH:MM",
        "location": "Specific location or area",
        "weather_sensitive": false,
        "risk_note": null
      }},
      ...more steps...
    ],
    "reasoning": "Why this plan works with current weather and travel constraints"
  }},
  "plan_b": {{ ... }} or null,
  "overall_risk": "low" or "medium" or "high",
  "weather_note": "Human-friendly weather and travel advice"
}}

Generate the plan NOW:"""
    
    return prompt


async def call_llm(prompt: str, llm_client=None) -> Optional[str]:
    """Call your LLM (Gemini, Claude, etc.)."""
    
    # TODO: Replace with real LLM integration
    print("(Using mock LLM response for demo)")
    
    mock_response = """{
  "activity": "Beach day with dining",
  "location": "Goa, India",
  "date": "2026-03-16",
  "feasible": true,
  "feasibility_note": "Goa is a coastal state perfect for beach activities and dining",
  "plan_a": {
    "name": "Beach Day with Local Cuisine",
    "summary": "Start with beach activities, transition to lunch at a nearby restaurant, finish with sunset at the beach",
    "steps": [
      {
        "order": 1,
        "description": "Travel to Goa from Delhi (flight + hotel check-in)",
        "time_from": "08:00",
        "time_to": "14:00",
        "location": "Travel + Hotel",
        "weather_sensitive": false,
        "risk_note": "Account for flight and transfer time"
      },
      {
        "order": 2,
        "description": "Rest and freshen up at hotel",
        "time_from": "14:00",
        "time_to": "15:30",
        "location": "Hotel",
        "weather_sensitive": false,
        "risk_note": null
      },
      {
        "order": 3,
        "description": "Visit Calangute Beach for swimming and sunbathing",
        "time_from": "15:30",
        "time_to": "18:00",
        "location": "Calangute Beach",
        "weather_sensitive": true,
        "risk_note": "Wear sunscreen - high UV index. Sun will still be strong"
      },
      {
        "order": 4,
        "description": "Dinner at nearby Coastal Kitchen restaurant (highly rated)",
        "time_from": "18:30",
        "time_to": "20:00",
        "location": "Coastal Kitchen, Calangute",
        "weather_sensitive": false,
        "risk_note": null
      },
      {
        "order": 5,
        "description": "Evening walk and dessert at Beach Shack Cafe",
        "time_from": "20:00",
        "time_to": "21:30",
        "location": "Beach Shack Cafe",
        "weather_sensitive": false,
        "risk_note": "Perfect weather for evening stroll"
      }
    ],
    "reasoning": "This plan optimizes for travel constraints (accounting for flight from Delhi) and uses nearby rated attractions. Activities are grouped by proximity to minimize additional travel. Weather is excellent for beach, so no alternative needed."
  },
  "plan_b": null,
  "overall_risk": "low",
  "weather_note": "Sunny with light breeze from the ocean. You'll feel warm and refreshed. Wear light clothes, sunscreen, and a hat. The sea breeze will keep you cool even in the sun. Ideal beach weather!"
}"""
    
    return mock_response


def extract_json_from_response(response: str) -> str:
    """Extract JSON from LLM response."""
    if "```json" in response:
        start = response.find("```json") + 7
        end = response.find("```", start)
        return response[start:end].strip()
    
    if "```" in response:
        start = response.find("```") + 3
        end = response.find("```", start)
        return response[start:end].strip()
    
    return response.strip()


# ──────────────────────────────────────────────────────────────────
# TEST SCENARIOS
# ──────────────────────────────────────────────────────────────────

async def main():
    """Test the geolocation-enabled pipeline."""
    
    print("\n" + "🌍 CHRONOS WITH GOOGLE MAPS INTEGRATION")
    print("=" * 70)
    print("This example shows:")
    print("1. User geolocation detection (IP-based)")
    print("2. Travel time estimation")
    print("3. Nearby place discovery")
    print("4. Location-aware activity grouping")
    print("=" * 70)
    
    # Test Case 1: Beach day in Goa
    print("\n\n📍 TEST CASE 1: Beach Day in Goa (with Travel from Delhi)")
    result = await plan_with_geolocation(
        activity="beach day with dining",
        destination_location="Goa, India",
        forecast_date="2026-03-16",
    )
    
    if result:
        print("\n✅ SUCCESS - Full plan generated with geolocation awareness")
    
    # Test Case 2: Invalid location
    print("\n\n📍 TEST CASE 2: Museum Tour in Non-existent Location")
    result = await plan_with_geolocation(
        activity="museum tour",
        destination_location="FakeCity, Mars",
        forecast_date="2026-03-16",
    )
    
    if not result:
        print("\n❌ BLOCKED (as expected) - Location doesn't exist")


if __name__ == "__main__":
    asyncio.run(main())
