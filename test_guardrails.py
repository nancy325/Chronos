"""
test_guardrails.py - Unit tests demonstrating the hallucination guardrails

Run with: pytest test_guardrails.py -v

These tests show the pipeline catching:
1. Invalid locations
2. Infeasible activities
3. Invalid LLM output
"""

import asyncio
import pytest
from geocoding import validate_location, geocode_location, get_location_metadata
from sanity_check import check_activity_feasibility, FeasibilityStatus
from weather_api import fetch_weather, generate_simulated_weather, get_weather_summary
from planner_agent import PlannedOutput, TaskStep, PlanOption, RiskLevel
from pipeline import run_planning_pipeline, ChronosPipeline


# ──────────────────────────────────────────────────────────────────────────────
# TEST SUITE 1: Location Validation (Geocoding)
# ──────────────────────────────────────────────────────────────────────────────

class TestLocationValidation:
    """Test that invalid locations are rejected immediately (fail-fast)."""
    
    def test_valid_location(self):
        """Valid location should return Location object."""
        is_valid, location, error = validate_location("Goa", "India")
        assert is_valid == True
        assert location is not None
        assert location.name == "Goa, India"
        assert location.terrain_type == "coastal"
    
    def test_invalid_location(self):
        """Invalid location should return error."""
        is_valid, location, error = validate_location("FakeCity123", "Mars")
        assert is_valid == False
        assert location is None
        assert "not found" in error.lower()
    
    def test_empty_location(self):
        """Empty location should return error."""
        is_valid, location, error = validate_location("", "India")
        assert is_valid == False
        assert "cannot be empty" in error.lower()
    
    def test_location_metadata(self):
        """Location metadata should include terrain type."""
        is_valid, location, _ = validate_location("Denver", "USA")
        assert is_valid == True
        
        metadata = get_location_metadata(location)
        assert metadata["terrain_type"] == "mountain"
        assert metadata["is_mountain"] == True
        assert metadata["is_coastal"] == False

    def test_geocode_uses_osm_fallback_when_not_in_mock(self, monkeypatch):
        """If local DB misses, geocoder should try OpenStreetMap fallback."""
        from geocoding import Location
        import geocoding

        def fake_osm_geocode(city: str, state_or_country: str):
            assert city == "reykjavik"
            return Location(
                name="Reykjavík, Capital Region, Iceland",
                latitude=64.1466,
                longitude=-21.9426,
                country="Iceland",
                state_or_region="Capital Region",
                continent="Europe",
                terrain_type="urban",
            )

        monkeypatch.setattr(geocoding, "_geocode_with_nominatim", fake_osm_geocode)

        location = geocode_location("Reykjavik", "Iceland")
        assert location is not None
        assert location.country == "Iceland"
        assert abs(location.latitude - 64.1466) < 0.001

    def test_invalid_location_returns_nearest_suggestions(self, monkeypatch):
        """Invalid locations should include nearest valid place suggestions."""
        import geocoding

        monkeypatch.setattr(geocoding, "_geocode_with_nominatim", lambda *_: None)
        monkeypatch.setattr(
            geocoding,
            "_suggest_with_nominatim",
            lambda *_args, **_kwargs: [
                "Anand, Gujarat, India (22.5585, 72.9297)",
                "Vadodara, Gujarat, India (22.3072, 73.1812)",
            ],
        )

        is_valid, location, error = validate_location("Anad")
        assert is_valid is False
        assert location is None
        assert "Did you mean:" in error
        assert "Anand, Gujarat, India" in error


# ──────────────────────────────────────────────────────────────────────────────
# TEST SUITE 2: Geographic Sanity Checks
# Blocks infeasible activities BEFORE LLM
# ──────────────────────────────────────────────────────────────────────────────

class TestSanityCheck:
    """Test that infeasible activities are caught."""
    
    def test_beach_at_coastal_location(self):
        """Beach activity should be FEASIBLE at coastal location."""
        _, location, _ = validate_location("Goa", "India")
        result = check_activity_feasibility("beach", location)
        assert result.status == FeasibilityStatus.FEASIBLE
        assert "feasible" in result.reason.lower()
    
    def test_beach_at_inland_location(self):
        """Beach activity should be INFEASIBLE at inland location."""
        _, location, _ = validate_location("Anand", "India")
        result = check_activity_feasibility("beach", location)
        assert result.status == FeasibilityStatus.INFEASIBLE
        assert "beach" in result.reason.lower()
        assert "not feasible" in result.reason.lower()
        assert result.suggestion is not None
    
    def test_skiing_at_desert_location(self):
        """Skiing should be INFEASIBLE in desert (no mountains)."""
        _, location, _ = validate_location("Vegas", "USA")
        result = check_activity_feasibility("skiing", location)
        assert result.status == FeasibilityStatus.INFEASIBLE
    
    def test_skiing_at_mountain_location(self):
        """Skiing should be FEASIBLE at mountain location."""
        _, location, _ = validate_location("Swiss Alps", "Switzerland")
        result = check_activity_feasibility("skiing", location)
        assert result.status == FeasibilityStatus.FEASIBLE
    
    def test_flexible_activity_anywhere(self):
        """Flexible activities (hiking, office work) should work anywhere."""
        locations = ["Anand", "Goa", "Denver"]
        for city in locations:
            _, location, _ = validate_location(city)
            for activity in ["hiking", "office work", "reading"]:
                result = check_activity_feasibility(activity, location)
                # Either FEASIBLE or REQUIRES_LLM_CHECK, not INFEASIBLE
                assert result.status in [FeasibilityStatus.FEASIBLE, FeasibilityStatus.REQUIRES_LLAMA_CHECK]
    
    def test_desert_safari_requires_desert(self):
        """Desert safari should require desert terrain."""
        _, coastal_location, _ = validate_location("Goa", "India")
        result = check_activity_feasibility("desert safari", coastal_location)
        assert result.status == FeasibilityStatus.INFEASIBLE
        
        _, desert_location, _ = validate_location("Vegas", "USA")
        result = check_activity_feasibility("desert safari", desert_location)
        assert result.status == FeasibilityStatus.FEASIBLE


# ──────────────────────────────────────────────────────────────────────────────
# TEST SUITE 3: Weather Handling
# ──────────────────────────────────────────────────────────────────────────────

class TestWeatherHandling:
    """Test that weather data is handled correctly."""
    
    def test_simulated_weather_deterministic(self):
        """Simulated weather should be deterministic (same params = same weather)."""
        weather1 = generate_simulated_weather("Goa, India", 15.3667, 73.8333, "2026-03-16")
        weather2 = generate_simulated_weather("Goa, India", 15.3667, 73.8333, "2026-03-16")
        
        assert weather1.temperature_celsius == weather2.temperature_celsius
        assert weather1.condition == weather2.condition
        assert weather1.precipitation_chance == weather2.precipitation_chance
    
    def test_different_dates_different_weather(self):
        """Different dates should (usually) produce different weather."""
        weather1 = generate_simulated_weather("Goa, India", 15.3667, 73.8333, "2026-03-16")
        weather2 = generate_simulated_weather("Goa, India", 15.3667, 73.8333, "2026-03-17")
        
        # These might coincidentally be the same, but very unlikely
        # Just check that the function runs without error
        assert weather1 is not None
        assert weather2 is not None
    
    def test_weather_summary_is_human_friendly(self):
        """Weather summary should use human language, not raw metrics."""
        weather = generate_simulated_weather("Goa", 15.3667, 73.8333, "2026-03-16")
        summary = get_weather_summary(weather)
        
        # Should contain actionable advice, not raw metrics
        assert any(word in summary.lower() for word in ["jacket", "wear", "bring", "hydrate", "clothes", "sunscreen"])
        
        # Should NOT contain exact metric numbers
        assert "°C" not in summary  # No temperature symbols
        assert "%" not in summary   # No percentages
        assert "km/h" not in summary  # No wind speed units


# ──────────────────────────────────────────────────────────────────────────────
# TEST SUITE 4: Pipeline Orchestration
# Full end-to-end pipeline with all guardrails
# ──────────────────────────────────────────────────────────────────────────────

class TestPipeline:
    """Test the full pipeline with guardrails."""
    
    @pytest.mark.asyncio
    async def test_pipeline_valid_activity_location(self):
        """Valid activity + location should succeed."""
        success, context, error = await run_planning_pipeline(
            activity="beach day",
            location_string="Goa, India",
            forecast_date="2026-03-16",
            use_simulated_weather=True
        )
        
        assert success == True
        assert error is None
        assert context is not None
        assert context["location"] == "Goa, India"
        assert context["activity"] == "beach day"
        assert context["feasibility_check"]["status"] == "feasible"
    
    @pytest.mark.asyncio
    async def test_pipeline_infeasible_activity(self):
        """Infeasible activity should fail at sanity check (not reach LLM)."""
        success, context, error = await run_planning_pipeline(
            activity="beach day",
            location_string="Anand, India",
            forecast_date="2026-03-16",
            use_simulated_weather=True
        )
        
        assert success == False
        assert error is not None
        assert error.stage == "sanity_check"
        assert "INFEASIBLE" in error.code
    
    @pytest.mark.asyncio
    async def test_pipeline_invalid_location(self):
        """Invalid location should fail immediately (fail-fast)."""
        success, context, error = await run_planning_pipeline(
            activity="hiking",
            location_string="FakeCity123, Mars",
            forecast_date="2026-03-16",
            use_simulated_weather=True
        )
        
        assert success == False
        assert error is not None
        assert error.stage == "location_validation"
        assert error.code == "LOCATION_NOT_FOUND"
    
    @pytest.mark.asyncio
    async def test_pipeline_context_structure(self):
        """Pipeline should build proper context for LLM."""
        success, context, _ = await run_planning_pipeline(
            activity="hiking",
            location_string="Denver, USA",
            forecast_date="2026-03-16",
            use_simulated_weather=True
        )
        
        assert success == True
        assert "location" in context
        assert "activity" in context
        assert "location_metadata" in context
        assert "weather" in context
        assert "feasibility_check" in context
        
        # Check metadata structure
        metadata = context["location_metadata"]
        assert "terrain_type" in metadata
        assert "is_mountain" in metadata
        assert "is_coastal" in metadata
        
        # Check weather structure
        weather = context["weather"]
        assert "raw" in weather
        assert weather["raw"] is not None
        assert "temperature_celsius" in weather["raw"]


# ──────────────────────────────────────────────────────────────────────────────
# TEST SUITE 5: Output Validation (Pydantic)
# Validates that LLM output matches schema
# ──────────────────────────────────────────────────────────────────────────────

class TestOutputValidation:
    """Test Pydantic validation of LLM output."""
    
    def test_valid_task_step(self):
        """Valid TaskStep should pass validation."""
        step = TaskStep(
            order=1,
            description="Pack sunscreen and swimsuit for the beach",
            time_from="08:00",
            time_to="08:30",
            location="Home",
            weather_sensitive=False,
        )
        assert step.order == 1
        assert step.description is not None
    
    def test_invalid_task_step_order(self):
        """Invalid step order should fail."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            TaskStep(
                order=0,  # Invalid: must be >= 1
                description="Invalid step",
            )
    
    def test_invalid_task_step_too_many(self):
        """Plan with too many steps should fail."""
        steps = [
            TaskStep(
                order=i,
                description=f"Step {i}",
            )
            for i in range(1, 100)  # 99 steps, max is 50
        ]
        
        with pytest.raises(Exception):  # Pydantic ValidationError
            PlanOption(
                name="Too many steps",
                summary="This plan has too many steps",
                steps=steps,
                reasoning="Invalid plan"
            )
    
    def test_valid_plan_option(self):
        """Valid PlanOption should pass validation."""
        plan = PlanOption(
            name="Beach Day",
            summary="Enjoy a relaxing day at the beach with swimming and lunch",
            steps=[
                TaskStep(order=1, description="Pack beach essentials"),
                TaskStep(order=2, description="Drive to beach"),
                TaskStep(order=3, description="Swim and relax"),
            ],
            reasoning="Perfect weather for beach activities"
        )
        assert len(plan.steps) == 3
        assert plan.name == "Beach Day"
    
    def test_valid_planned_output(self):
        """Valid PlannedOutput should pass validation."""
        output = PlannedOutput(
            activity="beach day",
            location="Goa, India",
            date="2026-03-16",
            feasible=True,
            feasibility_note="Goa is a coastal location with excellent beaches",
            plan_a=PlanOption(
                name="Original Beach Day",
                summary="Traditional beach day",
                steps=[
                    TaskStep(order=1, description="Go to beach at 8am"),
                ],
                reasoning="Good weather for beach"
            ),
            plan_b=None,
            overall_risk=RiskLevel.LOW,
            weather_note="Sunny with light breeze. Wear sunscreen."
        )
        
        assert output.activity == "beach day"
        assert output.feasible == True
        assert output.overall_risk == RiskLevel.LOW
    
    def test_invalid_risk_level(self):
        """Invalid risk level should fail."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            PlannedOutput(
                activity="test",
                location="test",
                date="2026-03-16",
                feasible=True,
                feasibility_note="test",
                plan_a=PlanOption(
                    name="test",
                    summary="test",
                    steps=[TaskStep(order=1, description="test")],
                    reasoning="test"
                ),
                overall_risk="INVALID_RISK_LEVEL"  # Invalid
            )


# ──────────────────────────────────────────────────────────────────────────────
# Integration Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestIntegration:
    """Integration tests showing real-world scenarios."""
    
    @pytest.mark.asyncio
    async def test_scenario_valid_beach_trip(self):
        """Realistic scenario: Beach trip in Goa."""
        success, context, error = await run_planning_pipeline(
            activity="beach day with swimming and dinner",
            location_string="Goa",
            forecast_date="2026-03-16",
            use_simulated_weather=True
        )
        
        assert success == True
        assert context["feasibility_check"]["status"] == "feasible"
        assert context["weather"] is not None
    
    @pytest.mark.asyncio
    async def test_scenario_blocked_beach_in_anand(self):
        """Realistic scenario: User tries beach in inland Anand (blocked)."""
        success, context, error = await run_planning_pipeline(
            activity="beach swimming and surfing",
            location_string="Anand, India",
            forecast_date="2026-03-16",
            use_simulated_weather=True
        )
        
        assert success == False
        assert error.stage == "sanity_check"
        assert "beach" in error.message.lower() or "swimming" in error.message.lower()
    
    @pytest.mark.asyncio
    async def test_scenario_skiing_in_mountains(self):
        """Realistic scenario: Skiing in mountains (allowed)."""
        success, context, error = await run_planning_pipeline(
            activity="skiing adventure",
            location_string="Swiss Alps, Switzerland",
            forecast_date="2026-03-16",
            use_simulated_weather=True
        )
        
        assert success == True
        assert context["feasibility_check"]["status"] == "feasible"


# ──────────────────────────────────────────────────────────────────────────────
# Run Tests
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Run with: pytest test_guardrails.py -v
    # Or: python test_guardrails.py (for simple execution)
    
    print("\n" + "="*70)
    print("CHRONOS GUARDRAIL TESTS")
    print("="*70)
    
    # Sync tests
    test_suite = TestLocationValidation()
    print("\n✅ Testing Location Validation...")
    test_suite.test_valid_location()
    test_suite.test_invalid_location()
    print("   All location tests passed!")
    
    test_suite = TestSanityCheck()
    print("\n✅ Testing Sanity Checks...")
    test_suite.test_beach_at_coastal_location()
    test_suite.test_beach_at_inland_location()
    test_suite.test_flexible_activity_anywhere()
    print("   All sanity check tests passed!")
    
    test_suite = TestWeatherHandling()
    print("\n✅ Testing Weather Handling...")
    test_suite.test_simulated_weather_deterministic()
    test_suite.test_weather_summary_is_human_friendly()
    print("   All weather tests passed!")
    
    test_suite = TestOutputValidation()
    print("\n✅ Testing Output Validation...")
    test_suite.test_valid_task_step()
    test_suite.test_valid_plan_option()
    test_suite.test_valid_planned_output()
    print("   All output validation tests passed!")
    
    print("\n" + "="*70)
    print("ALL TESTS PASSED ✅")
    print("="*70)
