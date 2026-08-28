# TravelAI Companion 🌍✈️

**TravelAI Companion** is an AI-powered travel recommendation and planning platform built with Python, Flask, scikit-learn, Bootstrap 5, Leaflet.js (OpenStreetMap), Geoapify Places & Geocoding APIs, and OpenWeatherMap API.

---

## 🌟 Key Features

1. **User Authentication & Profiles**: Register, login, session management (Flask-Login), Werkzeug password hashing, and profile management with avatar uploads.
2. **AI Destination Recommender Engine**: TF-IDF vectorization and cosine similarity algorithm matching user budget, travel category, interests, and preferred regions across ~80+ destinations (`ml/recommender.py`).
3. **Hotel Finder (Geoapify Places API)**: Nearby accommodation search with budget filtering, rating sorting, map pins, and SQLite response caching (`HotelsCache`).
4. **Live Weather Dashboard (OpenWeatherMap API)**: Real-time temperature, humidity, wind metrics, and 5-day weather forecasts.
5. **Nearby Attractions Finder (Geoapify + OpenStreetMap)**: Interactive Leaflet.js map with tourist attraction pins and distance listings.
6. **AI Day-by-Day Itinerary Generator**: Multi-day itinerary planning with spatial proximity sorting of attractions.
7. **Community Social Feed**: Post captions, photo uploads, Geoapify geocoded location tags, AJAX likes, and flat comments.

---

## 🏗 Tech Stack

- **Backend**: Python 3.13 + Flask
- **Database**: SQLite via SQLAlchemy ORM
- **Machine Learning**: `scikit-learn` (TfidfVectorizer + Cosine Similarity), `pandas`, `numpy`
- **Frontend**: Jinja2 Templates, Bootstrap 5, Leaflet.js (OpenStreetMap), Vanilla JavaScript
- **Auth & Security**: Flask-Login, Werkzeug, Flask-WTF / WTForms with server-side validation & `bleach` XSS sanitization

---

## 🔑 External API Keys Setup

The app requires two external API services (both offer free tiers):

1. **OpenWeatherMap API**:
   - Register at [https://openweathermap.org/api](https://openweathermap.org/api)
   - Copy your API Key under **API keys**.
2. **Geoapify Places & Geocoding API**:
   - Register at [https://www.geoapify.com/](https://www.geoapify.com/)
   - Create a project and copy your API Key.

> 💡 **Graceful Fallback Mode**: If API keys are left blank or calls fail/time out, the app automatically uses built-in realistic fallback data so all features remain fully functional without breaking!

---

## 🚀 Installation & Running Guide

### 1. Clone or Navigate to Project Directory
```bash
cd C:\Users\siddh\.gemini\antigravity\scratch\TravelAI
```

### 2. Environment Variables Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env` to include your keys:
```env
SECRET_KEY=your_custom_secret_key_2026
OPENWEATHER_API_KEY=your_openweather_key_here
GEOAPIFY_API_KEY=your_geoapify_key_here
DATABASE_URI=sqlite:///travel_ai.db
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Application
```bash
python app.py
```
Open your browser at [http://127.0.0.1:5000](http://127.0.0.1:5000).

---

## 🧪 Running Automated Tests

Run the test suite using `pytest`:
```bash
pytest tests/test_app.py -v
```

---

## 📂 Project Structure

```
TravelAI/
├── app.py                  # Main Flask routes and app controller
├── models.py               # SQLAlchemy ORM models (User, Destination, HotelsCache, Post, Like, Comment)
├── forms.py                # WTForms with validation and bleach XSS sanitization
├── config.py               # Application configuration & env loading
├── requirements.txt        # Python package dependencies
├── .env.example            # Environment variables template
├── README.md               # Setup and usage guide
├── FUTURE_ENHANCEMENTS.md  # Deferred features & roadmap documentation
├── static/
│   ├── css/custom.css      # Custom styling
│   ├── js/main.js          # Leaflet map helpers & AJAX logic
│   └── uploads/            # Profile photos & community uploads
├── templates/              # Jinja2 HTML templates
├── datasets/
│   └── destinations.csv    # Real travel destinations dataset
├── ml/
│   └── recommender.py      # TF-IDF + Cosine similarity recommender engine
├── api/
│   ├── weather.py          # OpenWeatherMap integration wrapper
│   └── geoapify.py         # Geoapify Places, Geocoding & OSM wrapper
└── tests/
    └── test_app.py         # Pytest automated test suite
```
