# TravelAI Companion 🌍✈️

**TravelAI Companion** is a full-stack, AI-powered travel recommendation, discovery, and planning platform built with Python, Flask, scikit-learn, Bootstrap 5, Leaflet.js (OpenStreetMap), Google Gemini AI, Geoapify Places & Geocoding APIs, and OpenWeatherMap API.

Designed with a rich focus on authentic Indian and international travel, the platform helps travelers find personalized destinations, explore accommodations matching their budget, plan customizable day-by-day itineraries, check live weather forecasts, and consult a 24/7 personalized AI travel companion.

---

## 🌟 Key Features

### 1. 🇮🇳 500 Curated Destinations & ML Recommender Engine
- **Expanded Dataset**: 500 distinct destinations across all Indian states and Union Territories (Himachal, Uttarakhand, Jammu & Kashmir, Ladakh, Rajasthan, Goa, Kerala, Karnataka, North East India, Andaman & Nicobar, Lakshadweep) as well as iconic international hubs (`datasets/destinations.csv`).
- **TF-IDF + Cosine Similarity Recommender**: Classical Information Retrieval engine (`ml/recommender.py`) that matches traveler preferences against destination categories, regional tags, and budget tiers.
- **Three Standardized Budget Categories**:
  - **Budget**: Under ₹15,000
  - **Moderate**: ₹15,000 – ₹50,000
  - **Luxury**: Above ₹50,000

### 2. 🤖 Personalized TravelAI Chatbot (Powered by Gemini AI)
- **Broad Travel Domain Expertise**: Beyond generating itineraries, TravelAI answers a wide range of real-world travel queries (`api/gemini.py`):
  - 🍲 **Local Cuisine & Food**: Iconic regional dishes, famous street markets, popular cafes, and dining costs.
  - 🚌 **Transit & Routes**: Volvo buses, Vande Bharat trains, flight connections, scenic drives, and scooter/bike rentals.
  - 🛡️ **Safety & Solo Travel**: Practical advice for solo and female travelers, safe neighborhoods, and national emergency helplines (**112**, **1091**, **1363**).
  - 💰 **Budget Hacks & Costs**: Money-saving strategies, UPI payments, and realistic expense breakdowns in INR (₹).
  - 🎒 **Packing & Climate Checklists**: 3-layer winter warmth for snow/mountains, beachwear, and monsoon gear.
  - 🌿 **Offbeat Escapes & Hidden Gems**: Peaceful, lesser-known alternatives to crowded tourist hubs.
  - 🛕 **Culture & Temple Etiquette**: Modest dress codes, footwear rules, and local customs.
  - 🪂 **Adventure & Outdoor Activities**: River rafting, paragliding, scuba diving, and trekking.
  - 🛂 **Visas & Domestic Permits**: Inner Line Permits (ILP) and visa-on-arrival guidelines.
- **Personalized & Context-Aware**: Greets authenticated users by name, captures active page/destination context, and supports quick prompt suggestion chips.
- **Strict Itinerary Accuracy**: When an itinerary is requested, generates a complete day-by-day plan covering the exact number of days requested (Day 1 through Day N) with Morning, Afternoon, and Evening schedules.
- **Resilient Architecture**: Dual integration via official `google-genai` SDK and direct REST fallback with exponential backoff retries on HTTP 503, plus rich offline knowledge fallbacks.

### 3. 🏨 Hotel Finder with Budget Sorting & Direct Website Links
- **Accurate Budget Sorting**: Filter and sort accommodations by budget (*Budget: Low to High*, *Budget: High to Low*, *Highest Rated*).
- **Nightly Rates in INR**: Nightly rates displayed across Budget (₹1,400–₹2,800/night), Moderate (₹4,800–₹8,900/night), and Luxury (₹18,500–₹38,000/night).
- **Direct Hotel Website Links**: Direct links to official websites or booking portals on hotel cards and OpenStreetMap map popups.
- **SQLite Caching Table**: `HotelsCache` persists search results to reduce external API overhead.

### 4. 📅 Customizable & Editable Day-by-Day Itineraries
- **Dynamic In-App Editing**: Users can edit activity timings, titles, and descriptions, add new activities to any day, insert additional days, and delete items with instant recalculation.
- **Geodesic Proximity Sorting**: Groups attractions by Haversine distance to minimize daily commute times.

### 5. 🗺️ Tourist Attractions & Live Weather
- **Tourist Attraction Finder**: Interactive Leaflet.js map with tourist attraction markers, addresses, and distance listings (`/tourist-attractions`).
- **Live Weather Dashboard**: Real-time temperature, humidity, wind metrics, and 5-day forecasts via OpenWeatherMap API.

### 6. 📸 Community Social Feed & Admin Moderation
- **Community Feed**: Share travel stories, upload travel photos, tag geocoded locations, like posts with AJAX, and participate in discussions.
- **Admin Photo Moderation**: Dedicated admin view (`/admin/photos`) for moderating uploaded images with instant deletion controls.
- **Admin Dashboard**: Destination management, user management, and hotel cache management.

### 7. 🔒 Authentication & Security
- **Robust Password Policy**: Minimum 8 characters requiring a mix of alphabetic letters, digits, and special characters.
- **Secure Hashing**: Password hashing using Werkzeug `scrypt`/`pbkdf2`.
- **Input Sanitization**: WTForms with `bleach` XSS sanitization and CSRF protection.
- **Role-Based Access Control**: Decorators safeguarding admin routes (`@admin_required`).

---

## 🏗 Tech Stack & Architecture

- **Backend**: Python 3.13 + Flask 3.1
- **Database**: SQLite via SQLAlchemy ORM
- **Machine Learning**: `scikit-learn` (TF-IDF + Cosine Similarity), `pandas`, `numpy`
- **Generative AI**: Google Gemini (`google-genai` SDK + Generative Language REST API)
- **External APIs**: Geoapify Places & Geocoding API, OpenWeatherMap API
- **Frontend**: Jinja2 Templates, Bootstrap 5, Leaflet.js (OpenStreetMap), Vanilla JavaScript
- **Auth & Security**: Flask-Login, Werkzeug, Flask-WTF, Bleach

---

## 🔑 External API Keys Setup

The application integrates three external services (all offer free tiers):

1. **Google Gemini API**:
   - Get an API key at [https://aistudio.google.com/](https://aistudio.google.com/)
2. **OpenWeatherMap API**:
   - Register at [https://openweathermap.org/api](https://openweathermap.org/api)
3. **Geoapify Places & Geocoding API**:
   - Register at [https://www.geoapify.com/](https://www.geoapify.com/)

> 💡 **Graceful Fallback Mode**: If API keys are unconfigured or calls time out, TravelAI automatically uses its rich built-in knowledge engines so all features remain functional.

---

## 🚀 Installation & Setup Guide

### 1. Clone or Navigate to Project Directory
```bash
git clone https://github.com/siddhi57/TravelAI.git
cd TravelAI
```

### 2. Environment Variables Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` with your configuration:
```env
SECRET_KEY=your_secure_random_secret_key
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
OPENWEATHER_API_KEY=your_openweather_key_here
GEOAPIFY_API_KEY=your_geoapify_key_here
DATABASE_URI=sqlite:///travel_ai.db
FLASK_DEBUG=False
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Seed Database Dataset
Seed the 500 destinations dataset into SQLite:
```bash
flask seed-db
```

### 5. Run Development Server
```bash
python app.py
```
Open your browser at `http://127.0.0.1:5000`.

---

## 🏭 Production WSGI Deployment

For production deployment with multiple worker processes using Gunicorn:
```bash
gunicorn --workers 4 --bind 0.0.0.0:8000 app:app
```

---

## 🧪 Running Automated Tests

Run the complete test suite using `pytest`:
```bash
pytest tests/test_app.py -v
```

All 19 test modules cover:
- Haversine distance calculations
- TF-IDF machine learning recommendations across 500 destinations
- Live & fallback weather wrapper
- Geoapify geocoding, hotels, and attractions
- Public routes and authenticated workflows
- Password complexity enforcement (8+ chars, mixed alphanumeric)
- Admin access control and dashboard statistics
- Admin photo moderation panel and community post management
- Gemini AI integration and HTTP 503 retry backoff
- Chatbot dynamic day-by-day itinerary generation
- Chatbot personalized multi-domain travel queries (food, transport, safety, budget, packing, culture)
- Interactive & editable itinerary generation

---

## 📂 Project Structure

```
TravelAI/
├── app.py                      # Main Flask routes, error handlers, and CLI commands
├── models.py                   # SQLAlchemy ORM models (User, Destination, HotelsCache, Post, Like, Comment)
├── forms.py                    # WTForms with validation and bleach XSS sanitization
├── config.py                   # Application configuration & env validation
├── requirements.txt            # Python package dependencies
├── .env.example                # Environment variables template
├── .gitignore                  # Git ignore rules
├── README.md                   # Project documentation and setup guide
├── FUTURE_ENHANCEMENTS.md      # Future roadmap documentation
├── static/
│   ├── css/custom.css          # Custom responsive styles & badges
│   ├── js/
│   │   ├── main.js             # Leaflet map initializers & AJAX helpers
│   │   ├── chatbot.js          # Chatbot controller with context capture
│   │   └── itinerary_editor.js # Interactive itinerary editor
│   └── uploads/                # User profile photos & community image uploads
├── templates/
│   ├── base.html               # Base navigation and footer layout
│   ├── index.html              # Landing page
│   ├── recommendations.html    # ML destination recommendation interface
│   ├── hotels.html             # Hotel Finder with budget sorting & links
│   ├── weather.html            # Live weather & forecast dashboard
│   ├── tourist_attractions.html# Tourist attraction map & listings
│   ├── itinerary.html          # Editable day-by-day travel itinerary
│   ├── community.html          # Social feed, photo sharing, comments
│   ├── components/
│   │   └── chatbot.html        # Floating personalized AI chatbot modal
│   └── admin/
│       ├── dashboard.html      # Admin overview metrics
│       ├── destinations.html   # Destination management
│       ├── users.html          # User management
│       └── photos.html         # Photo moderation view
├── datasets/
│   └── destinations.csv        # 500 curated destinations dataset
├── ml/
│   └── recommender.py          # TF-IDF & Cosine similarity recommender engine
├── api/
│   ├── gemini.py               # Personalized Gemini AI travel assistant
│   ├── weather.py              # OpenWeatherMap API wrapper
│   └── geoapify.py             # Geoapify Places, Geocoding & OSM wrapper
└── tests/
    └── test_app.py             # Pytest automated test suite (19 tests)
```
