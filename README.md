# TravelAI Companion 🌍✈️

**TravelAI Companion** is a travel recommendation and planning platform built with Python, Flask, scikit-learn, Bootstrap 5, Leaflet.js (OpenStreetMap), Geoapify Places & Geocoding APIs, and OpenWeatherMap API.

---

## 🌟 Key Features

1. **User Authentication & Profiles**: Register, login, session management (Flask-Login), Werkzeug password hashing, 8+ character password policy, and profile management with avatar uploads.
2. **TF-IDF Machine Learning Recommender Engine**: Utilizes classical Information Retrieval (IR) and Machine Learning techniques — `scikit-learn` `TfidfVectorizer` and `cosine_similarity` — to match user budget, travel category, interests, and preferred regions across 85+ destinations (`ml/recommender.py`).
3. **Hotel Finder (Geoapify Places API)**: Nearby accommodation search with budget filtering, rating sorting, map pins, and non-nullable SQLite response caching (`HotelsCache`).
4. **Live Weather Dashboard (OpenWeatherMap API)**: Real-time temperature, humidity, wind metrics, and 5-day weather forecasts.
5. **Nearby Attractions Finder (Geoapify + OpenStreetMap)**: Interactive Leaflet.js map with tourist attraction pins and distance listings.
6. **Day-by-Day Itinerary Generator**: Multi-day itinerary planning with geodesic Haversine distance proximity sorting.
7. **Community Social Feed**: Post captions, photo uploads, Geoapify geocoded location tags, pagination, AJAX likes, and flat comments.

---

## 🏗 Tech Stack & Architecture

- **Backend**: Python 3.13 + Flask 3.1
- **Database**: SQLite via SQLAlchemy ORM
- **Machine Learning**: `scikit-learn` (TF-IDF + Cosine Similarity), `pandas`, `numpy`
- **Frontend**: Jinja2 Templates, Bootstrap 5, Leaflet.js (OpenStreetMap), Vanilla JavaScript
- **Auth & Security**: Flask-Login, Werkzeug, Flask-WTF / WTForms with `bleach` XSS sanitization, environment-gated `SECRET_KEY` and `FLASK_DEBUG`.

---

## 🔑 External API Keys Setup

The app integrates two external API services (both offer free tiers):

1. **OpenWeatherMap API**:
   - Register at [https://openweathermap.org/api](https://openweathermap.org/api)
   - Copy your API Key under **API keys**.
2. **Geoapify Places & Geocoding API**:
   - Register at [https://www.geoapify.com/](https://www.geoapify.com/)
   - Create a project and copy your API Key.

> 💡 **Graceful Fallback Mode**: If API keys are left blank or calls fail/time out, the app automatically uses built-in realistic fallback data so all features remain fully functional without breaking.

---

## 🚀 Installation & Setup Guide

### 1. Clone or Navigate to Project Directory
```bash
cd C:\Users\siddh\.gemini\antigravity\scratch\TravelAI
```

### 2. Environment Variables Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env` to include your secrets and keys:
```env
SECRET_KEY=your_secure_256bit_random_key
OPENWEATHER_API_KEY=your_openweather_key_here
GEOAPIFY_API_KEY=your_geoapify_key_here
DATABASE_URI=sqlite:///travel_ai.db
FLASK_DEBUG=False
```

### 3. Install Pinned Dependencies
```bash
pip install -r requirements.txt
```

### 4. Seed Database Dataset
Seed the 85+ destinations dataset using the CLI command:
```bash
flask seed-db
```

### 5. Run Development Server
```bash
python app.py
```
Open your browser at [http://127.0.0.1:5000](http://127.0.0.1:5000).

---

## 🏭 Production WSGI Deployment (Gunicorn)

For production deployment with multiple worker processes:
```bash
gunicorn --workers 4 --bind 0.0.0.0:8000 app:app
```

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
├── app.py                  # Main Flask routes and CLI commands
├── models.py               # SQLAlchemy ORM models (users, destinations, hotels_cache, posts, likes, comments)
├── forms.py                # WTForms with validation and bleach XSS sanitization
├── config.py               # Application configuration & env validation
├── requirements.txt        # Pinned Python package dependencies
├── .env.example            # Environment variables template
├── .gitignore              # Ignored files (.env, *.db, uploads)
├── README.md               # Setup and deployment guide
├── FUTURE_ENHANCEMENTS.md  # Roadmap & deferred features documentation
├── static/
│   ├── css/custom.css      # Custom styling
│   ├── js/main.js          # Leaflet map helpers & AJAX logic
│   └── uploads/            # Profile photos & community uploads
├── templates/              # Jinja2 HTML templates
├── datasets/
│   └── destinations.csv    # 85+ travel destinations dataset
├── ml/
│   └── recommender.py      # TF-IDF & Cosine similarity recommender engine
├── api/
│   ├── weather.py          # OpenWeatherMap API integration wrapper
│   └── geoapify.py         # Geoapify Places, Geocoding & OSM wrapper
└── tests/
    └── test_app.py         # Pytest automated test suite
```
