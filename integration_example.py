"""
integration_example.py - Example integration of the full pipeline with LLM planning.

This shows how to:
1. Run the pipeline (guardrails)
2. Generate the planning prompt
3. Call an LLM (Gemini, Claude, etc.)
4. Validate the output against Pydantic schema
5. Return safe structured results to the user

Copy and adapt this for your actual LLM integration.
"""

import asyncio
import json
import os
from typing import Optional

# These are the new modules you've created
from pipeline import run_planning_pipeline
from planner_agent import (
    get_final_planner_prompt,
    PlannedOutput,
)


async def plan_with_chronos_v2(
    activity: str,
    location_string: str,
    forecast_date: str,
    llm_client = None,  # Pass your LLM client (Gemini, Claude, etc.)
) -> Optional[PlannedOutput]:
    """
    Full pipeline → LLM planning → structured output
    
    This is the main orchestration function.
    
    Args:
        activity: User's activity (e.g., "beach day", "hiking")
        location_string: User's location (e.g., "Anand, India")
        forecast_date: Date for planning (YYYY-MM-DD)
        llm_client: Your configured LLM client
        
    Returns:
        PlannedOutput (safe, validated) or None if pipeline fails
    """
    
    print("\n" + "="*70)
    print("STAGE 1: PIPELINE VALIDATION")
    print("="*70)
    
    # RUN THE PIPELINE
    # This validates location, checks feasibility, fetches weather
    success, context, error = await run_planning_pipeline(
        activity=activity,
        location_string=location_string,
        forecast_date=forecast_date,
        use_simulated_weather=True,  # Use simulated data for demo
    )
    
    if not success:
        print(f"\n❌ Pipeline Error: {error.message}")
        if error.suggestion:
            print(f"   Suggestion: {error.suggestion}")
        return None
    
    print(f"✅ Location validated: {context['location']}")
    print(f"✅ Activity feasible: {context['activity']}")
    if context['weather']:
        print(f"✅ Weather available: {context['weather']['raw']['condition']}")
    
    print("\n" + "="*70)
    print("STAGE 2: GENERATE PLANNING PROMPT")
    print("="*70)
    
    # BUILD THE PLANNING PROMPT
    planning_prompt = get_final_planner_prompt(
        activity=context['activity'],
        location_name=context['location'],
        terrain_type=context['location_metadata']['terrain_type'],
        country=context['location_metadata']['country'],
        latitude=context['location_metadata']['latitude'],
        longitude=context['location_metadata']['longitude'],
        forecast_date=context['forecast_date'],
        weather_data=context['weather']['raw'] if context['weather'] else None,
    )
    
    print("\nPrompt (first 500 chars):")
    print(planning_prompt[:500] + "...")
    
    print("\n" + "="*70)
    print("STAGE 3: CALL LLM")
    print("="*70)
    
    # CALL THE LLM
    llm_response_text = await call_llm(planning_prompt, llm_client)
    
    if not llm_response_text:
        print("❌ LLM call failed")
        return None
    
    print("\nLLM Response (first 300 chars):")
    print(llm_response_text[:300] + "...")
    
    print("\n" + "="*70)
    print("STAGE 4: PARSE AND VALIDATE OUTPUT")
    print("="*70)
    
    # PARSE AND VALIDATE
    try:
        # Extract JSON from response (LLM might wrap it in markdown)
        json_str = extract_json_from_response(llm_response_text)
        response_data = json.loads(json_str)
        
        # Validate against Pydantic schema
        planned = PlannedOutput(**response_data)
        
        print("✅ Output validated against schema")
        print(f"✅ Generated {len(planned.plan_a.steps)} steps for Plan A")
        if planned.plan_b:
            print(f"✅ Generated {len(planned.plan_b.steps)} steps for Plan B")
        
        return planned
        
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON from LLM: {e}")
        print(f"   Raw response: {llm_response_text[:200]}")
        return None
    except Exception as e:
        print(f"❌ Validation error: {e}")
        return None


async def call_llm(prompt: str, llm_client = None) -> Optional[str]:
    """
    Call your LLM (Gemini, Claude, etc.).
    
    This is a placeholder — replace with your actual LLM integration.
    
    Args:
        prompt: The planning prompt
        llm_client: Your configured LLM client
        
    Returns:
        LLM response as string
    """
    
    # EXAMPLE 1: Using Google Gemini (if you have google-generativeai installed)
    # Uncomment and fill in your actual implementation
    
    """
    if llm_client is None:
        # Try to import and configure Gemini
        try:
            import google.generativeai as genai
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                print("❌ GEMINI_API_KEY not set in environment")
                return None
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            return response.text
        except ImportError:
            print("❌ google-generativeai not installed")
            return None
    """
    
    # EXAMPLE 2: Using Anthropic Claude
    """
    if llm_client is None:
        try:
            from anthropic import Anthropic
            client = Anthropic()
            message = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text
        except ImportError:
            print("❌ anthropic not installed")
            return None
    """
    
    # DEMO: Return a mock response for testing
    print("(Using mock LLM response for demo)")
    mock_response = """{
  "activity": "Beach day",
  "location": "Goa, India",
  "date": "2026-03-16",
  "feasible": true,
  "feasibility_note": "Goa is a coastal state with excellent beaches perfect for a beach day.",
  "plan_a": {
    "name": "Classic Beach Day",
    "summary": "Enjoy a perfect day at the beach with swimming and relaxation",
    "steps": [
      {
        "order": 1,
        "description": "Pack your beach essentials including sunscreen, hat, and swimsuit",
        "time_from": "07:00",
        "time_to": "07:30",
        "location": "Home",
        "weather_sensitive": false,
        "risk_note": null
      },
      {
        "order": 2,
        "description": "Head to Calangute Beach for morning swimming",
        "time_from": "08:00",
        "time_to": "10:30",
        "location": "Calangute Beach",
        "weather_sensitive": true,
        "risk_note": "Apply sunscreen regularly - the sun is strong today"
      },
      {
        "order": 3,
        "description": "Enjoy lunch at a beachside cafe with refreshing drinks",
        "time_from": "12:30",
        "time_to": "13:30",
        "location": "Beachside Cafe",
        "weather_sensitive": false,
        "risk_note": null
      }
    ],
    "reasoning": "This plan makes the most of perfect sunny weather while managing UV exposure through strategic timing."
  },
  "plan_b": null,
  "overall_risk": "low",
  "weather_note": "Sunny skies and warm temperatures mean you'll feel comfortable in light clothing. Bring sunscreen and reapply often - the UV index is high. Stay hydrated throughout the day."
}"""
    
    return mock_response


def extract_json_from_response(response: str) -> str:
    """
    Extract JSON from an LLM response.
    
    LLMs sometimes wrap JSON in markdown code blocks, so this handles that.
    
    Args:
        response: LLM response (may contain markdown)
        
    Returns:
        Clean JSON string
    """
    # If wrapped in markdown code fence
    if "```json" in response:
        start = response.find("```json") + 7
        end = response.find("```", start)
        return response[start:end].strip()
    
    if "```" in response:
        start = response.find("```") + 3
        end = response.find("```", start)
        return response[start:end].strip()
    
    # Already clean JSON
    return response.strip()


# ──────────────────────────────────────────────────────────────────────────────
# TEST/DEMO
# ──────────────────────────────────────────────────────────────────────────────

async def main():
    """Demo the full pipeline."""
    
    print("\n" + "🌍 CHRONOS v2 - Hallucination-Resistant Planner")
    print("=" * 70)
    
    # TEST CASE 1: Valid location + activity
    print("\n\nTEST CASE 1: Valid Beach Day in Goa")
    result = await plan_with_chronos_v2(
        activity="beach day",
        location_string="Goa, India",
        forecast_date="2026-03-16",
    )
    
    if result:
        print(f"\n✅ SUCCESS")
        print(f"   Activity: {result.activity}")
        print(f"   Location: {result.location}")
        print(f"   Risk Level: {result.overall_risk}")
        print(f"   Plan A has {len(result.plan_a.steps)} steps")
    
    # TEST CASE 2: Invalid location
    print("\n\nTEST CASE 2: Invalid Location (Beach in Inland City)")
    result = await plan_with_chronos_v2(
        activity="beach day",
        location_string="Anand, India",
        forecast_date="2026-03-16",
    )
    
    if not result:
        print("❌ BLOCKED (as expected) — Pipeline caught the infeasible activity")
    
    # TEST CASE 3: Location doesn't exist
    print("\n\nTEST CASE 3: Non-existent Location")
    result = await plan_with_chronos_v2(
        activity="hiking",
        location_string="FakeCity123, Mars",
        forecast_date="2026-03-16",
    )
    
    if not result:
        print("❌ BLOCKED (as expected) — Pipeline caught the invalid location")


if __name__ == "__main__":
    asyncio.run(main())
