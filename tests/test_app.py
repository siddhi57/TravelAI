import os
import sys
import pytest

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, db
from models import User, Destination, Post, Like, Comment, HotelsCache
from ml.recommender import DestinationRecommender, recommender_engine
from api.weather import get_current_weather, get_weather_forecast
from api.geoapify import geocode_location, get_nearby_hotels, get_nearby_attractions

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            # Seed test destination
            dest = Destination(
                name='Goa',
                state='Goa',
                category='Beach',
                budget_level='Moderate',
                description='Tropical beach destination in India',
                tags='beach nightlife water sports'
            )
            db.session.add(dest)
            db.session.commit()
        yield client

def test_ml_recommender():
    """Test TF-IDF recommender engine standalone."""
    recommender = DestinationRecommender()
    results = recommender.recommend(
        budget_level='Moderate',
        category='Beach',
        interests=['beach', 'nightlife'],
        top_n=5
    )
    assert len(results) > 0
    assert 'name' in results[0]
    assert 'score' in results[0]

def test_weather_api_wrapper():
    """Test OpenWeatherMap wrapper fallback & structure."""
    curr = get_current_weather('Goa')
    assert 'city' in curr
    assert 'temp' in curr
    assert 'condition' in curr
    
    fc = get_weather_forecast('Goa')
    assert 'forecast' in fc
    assert len(fc['forecast']) > 0

def test_geoapify_wrapper():
    """Test Geoapify places & geocoding wrapper fallback & structure."""
    coords = geocode_location('Goa')
    assert 'lat' in coords
    assert 'lng' in coords
    
    hotels = get_nearby_hotels('Goa', limit=5)
    assert len(hotels) > 0
    assert 'hotel_name' in hotels[0]
    
    attractions = get_nearby_attractions('Goa', limit=5)
    assert len(attractions) > 0
    assert 'name' in attractions[0]

def test_routes_public(client):
    """Test public route accessibility."""
    res = client.get('/')
    assert res.status_code == 200
    
    res = client.get('/recommendations')
    assert res.status_code == 200
    
    res = client.get('/hotels?destination=Goa')
    assert res.status_code == 200
    
    res = client.get('/weather?destination=Goa')
    assert res.status_code == 200
    
    res = client.get('/attractions?destination=Goa')
    assert res.status_code == 200
    
    res = client.get('/itinerary')
    assert res.status_code == 200

def test_auth_workflow(client):
    """Test user registration, login, profile, and logout."""
    # Register
    res = client.post('/register', data={
        'name': 'Test Traveler',
        'email': 'traveler@example.com',
        'password': 'password123',
        'confirm_password': 'password123'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'Account created successfully' in res.data or b'Sign In' in res.data
    
    # Login
    res = client.post('/login', data={
        'email': 'traveler@example.com',
        'password': 'password123'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'Welcome back' in res.data or b'Logout' in res.data
    
    # Profile view
    res = client.get('/profile')
    assert res.status_code == 200
    assert b'Test Traveler' in res.data
    
    # Logout
    res = client.get('/logout', follow_redirects=True)
    assert res.status_code == 200
