# Chronos – Weather-Adaptive Planning Assistant

> "Most apps tell you it's raining. Chronos tells you what to do about it." – HackIconics Team

Chronos is a weather-intelligent planning companion that fuses LLM reasoning with live (or simulated) meteorological data to generate optimized travel plans with dynamic durations, real tourist place recommendations, and practical packing guidance.

---

## 🎯 Key Features

✅ **Single Optimized Plan** — Generates ONE weather-adaptive plan instead of multiple options  
✅ **Real Tourist Places** — Uses OpenStreetMap APIs to suggest actual attractions, restaurants, temples (not generic locations)  
✅ **Dynamic Duration** — Parse flexible durations from user input ("2 weeks", "5 days", "1 week")  
✅ **Multi-Day Packing Lists** — For trips >1 day, includes practical packing essentials  
✅ **Weather Guardrails** — Fail-fast validation prevents impossible plans (e.g., beach in inland cities)  
✅ **Transparent Reasoning** — Shows decision trace and weather impact on recommendations  
✅ **Simulation Mode** — Works offline with deterministic weather for demos  

---

## 🏗️ Architecture

### 6-Stage Pipeline

```
Step 1: Parse User Prompt (Location, Activity, Duration)
    ↓
Step 2: Feasibility Check (Geocoding + Activity Validation)
    ↓ [FAIL FAST if invalid]
Step 3: Enrichment (Non-blocking parallel):
    • Fetch Weather Data (informational)
    • Detect User Location & Travel Time
    • Find Nearby Places (OpenStreetMap)
    ↓
Step 4: Duration Logic (dynamic parsing)
    ↓
Step 5: Context Preparation (aggregate Weather + Travel + Places)
    ↓
Step 6: Hand-off to planner_agent.py for LLM generation
```

### Tech Stack

- **Frontend**: Streamlit (interactive UI with session persistence)
- **LLM**: Google Gemini 2.5 Flash (via pydantic-ai)
- **APIs**:
  - **Location**: OpenStreetMap Nominatim (geocoding)
  - **Places**: OpenStreetMap Overpass QL (POI discovery)
  - **Weather**: wttr.in or OpenWeatherMap
  - **Geolocation**: IP-based fallback
- **Validation**: Pydantic 2 (strict schema enforcement)
- **Async**: asyncio + httpx (concurrent requests)

---

## 📁 Project Structure

```
Chronos/
├── app.py                          # Streamlit UI
├── agent.py                        # PydanticAI reasoning core
├── pipeline.py                     # 6-stage validation pipeline
├── planner_agent.py               # LLM prompt + output schemas
├── models.py                       # Pydantic data models
├── geocoding.py                    # Location validation (OSM Nominatim)
├── sanity_check.py                # Activity feasibility rules
├── weather_api.py                  # Weather fetching (wttr.in)
├── weather_advice.py              # Human-friendly weather guidance
├── user_location.py               # IP-based geolocation + travel time
├── google_maps_integration.py     # OpenStreetMap Overpass API (POI search)
├── tools.py                        # Utility tools for agent
├── utils.py                        # Helper functions
├── requirements.txt                # Dependencies
├── .env.example                    # Environment variable template
└── ARCHITECTURE_GUIDE.md           # Detailed technical documentation
```

---

## 🚀 Quick Start

### Installation

```bash
# Clone repo
git clone <repo-url>
cd Chronos

# Create virtual environment
python -m venv .venv-1
.venv-1\Scripts\activate  # Windows
source .venv-1/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Add your GEMINI_API_KEY to .env
```

### Run the App

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`

### Example Usage

1. **Input**: "Beach vacation in Goa for 1 week"
2. **App processes**:
   - Validates Goa is a real coastal location
   - Detects activity is "beach" (outdoor)
   - Fetches real weather
   - Parses duration as 7 days
   - Finds nearby beaches, restaurants, temples via OSM
3. **Output**:
   - 1 optimized plan with real place names ("Anjuna Beach", "Mango Tree Café", "Basilica of Bom Jesus")
   - Time-bounded steps for each day
   - Packing list: ["Lightweight clothing", "Sunscreen SPF 50+", "Water shoes", "Hat", "Camera"]
   - Weather advisory with practical tips

---

## 🔧 Configuration

### Environment Variables (`.env`)

```
GEMINI_API_KEY=your-api-key-here
SIMULATION_MODE=false  # Set to true for offline demos
```

### Simulation Mode

For testing without API keys, set `SIMULATION_MODE=true` in `.env`:
- Weather data becomes deterministic mock data
- OSM APIs are mocked with sample POIs
- Geolocation returns a default city

---

## 📊 How It Works

### Single Plan Generation

The planner receives a **PlannerContext** object containing:
- **Activity**: User's requested activity
- **Location**: Validated location with coordinates
- **Duration**: Parsed duration with start/end dates
- **Weather**: Actual weather data (never hallucinated)
- **Nearby Places**: Real POIs from OpenStreetMap
- **Travel Info**: User location → destination travel time estimate
- **Feasibility**: Pre-checked that activity is geographically viable

The LLM then generates **1 optimized plan** with:
- ✅ Real place names (from OSM list, not made up)
- ✅ Time-bounded steps (day-by-day for multi-day trips)
- ✅ Practical packing list (for multi-day only)
- ✅ Weather-sensitive flags on each activity
- ✅ Risk assessment (low/medium/high)

### Fallback Strategy

If LLM fails:
- App auto-switches to fallback plan generator
- Same structure, rule-based recommendations
- No service interruption in demos

---

## 🛡️ Safety Guardrails

1. **Location Validation** — Fail-fast on non-existent cities
2. **Activity Feasibility** — Block impossible activities (beach in desert)
3. **Weather Constraints** — Never hallucinate metrics
4. **Output Validation** — Pydantic rejects malformed LLM output
5. **Real Place Names** — LLM instructed to use OSM POI list, not invent locations

---

## 📝 Example Responses

### Single-Day Plan

**Input**: "Beach day at Goa"

**Output**:
```
📋 Your Plan
Risk Level: LOW ✅

⭐ Step 1: Head to the beach and set up your spot (09:00 - 10:00 @ Anjuna Beach)
⭐ Step 2: Enjoy swimming and beach games (10:00 - 13:00 @ Anjuna Beach)
⭐ Step 3: Grab lunch at a beach shack (13:00 - 14:00 @ Titos Cafe)
⭐ Step 4: Relax on the sand (14:00 - 17:00 @ Anjuna Beach)
```

### Multi-Day Plan with Packing List

**Input**: "Beach vacation in Goa for 1 week"

**Output**:
```
📋 Your Plan (7 Days)

🎒 What to Pack
• Light summer clothes
• Sunscreen SPF 50+
• Hat and sunglasses
• Comfortable walking shoes
• Refillable water bottle
• Beach cover-up
• Moisturizer (salt water dries skin)

📅 Friday, March 28, 2026
⭐ Step 1: Arrive and settle in (14:00 - 16:00 @ Your Resort)
⭐ Step 2: Explore local bazaar (17:00 - 19:00 @ Anjuna Market)

📅 Saturday, March 29, 2026
⭐ Step 1: Beach morning (08:00 - 11:00 @ Baga Beach)
⭐ Step 2: Water sports (11:00 - 13:00 @ Baga Water Sports)
...
```

---

## 💼 Use Cases

- 🏖️ **Personal Travel Planning** — Multi-day itineraries with weather adaptation
- 👰 **Event Coordination** — Outdoor ceremonies with rain contingencies
- 📦 **Logistics Routes** — Delivery scheduling around weather windows
- 🏫 **School Field Trips** — Educational excursions with backup plans
- ⚽ **Sports Events** — Tournament scheduling with weather awareness
- 🚨 **Emergency Response** — Critical aid distribution in adverse conditions

---

## 🤝 Contributing

Contributions welcome! Areas for enhancement:
- Real API integration (Google Maps, Mapbox)
- Multi-language support
- Advanced weather-based rescheduling
- User authentication & saved plans
- Mobile app version

---

## 📄 License

MIT License. See LICENSE file for details.

---

## 👨‍💻 Team

**HackIconics** — WiBD GenAI Hackathon 2026
