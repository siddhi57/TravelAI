import os
import sys

# Ensure test environment variables are set BEFORE importing app
os.environ['TESTING'] = 'True'
os.environ['DATABASE_URI'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test_secret_key_testing_mode_only'

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from app import app, db, haversine_distance_km
from models import User, Destination, Post, Like, Comment, HotelsCache
from ml.recommender import DestinationRecommender, recommender_engine
from api.weather import get_current_weather, get_weather_forecast
from api.geoapify import geocode_location, get_nearby_hotels, get_nearby_attractions
from api.gemini import ask_travel_gemini

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False
    
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
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

def test_haversine_distance():
    """Test geodesic distance calculation."""
    dist = haversine_distance_km(51.5074, -0.1278, 48.8566, 2.3522)
    assert 330 < dist < 360

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

def test_weather_api_wrapper():
    """Test OpenWeatherMap wrapper fallback & structure."""
    curr = get_current_weather('Goa')
    assert 'city' in curr
    assert 'temp' in curr
    
    fc = get_weather_forecast('Goa')
    assert 'forecast' in fc

def test_geoapify_wrapper():
    """Test Geoapify places & geocoding wrapper fallback & structure."""
    coords = geocode_location('Goa')
    assert 'lat' in coords
    
    hotels = get_nearby_hotels('Goa', limit=5)
    assert len(hotels) > 0
    
    attractions = get_nearby_attractions('Goa', limit=5)
    assert len(attractions) > 0

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

    res = client.get('/community?page=1')
    assert res.status_code == 200

def test_auth_workflow(client):
    """Test user registration, login, profile, and password length checks."""
    # Register with short password should fail
    res = client.post('/register', data={
        'name': 'Test Traveler',
        'email': 'traveler@example.com',
        'password': 'short',
        'confirm_password': 'short'
    }, follow_redirects=True)
    assert b'Password must be at least 8 characters long' in res.data

    # Valid Registration
    res = client.post('/register', data={
        'name': 'Test Traveler',
        'email': 'traveler@example.com',
        'password': 'password123',
        'confirm_password': 'password123'
    }, follow_redirects=True)
    assert res.status_code == 200
    
    # Login
    res = client.post('/login', data={
        'email': 'traveler@example.com',
        'password': 'password123'
    }, follow_redirects=True)
    assert res.status_code == 200
    
    # Logout
    res = client.get('/logout', follow_redirects=True)
    assert res.status_code == 200

def test_admin_access_control(client):
    """Test non-admin user receives 403 Forbidden on admin routes."""
    # Non-authenticated user
    res = client.get('/admin')
    assert res.status_code in (403, 302)

    # Register standard non-admin user
    client.post('/register', data={
        'name': 'Regular User',
        'email': 'user@example.com',
        'password': 'password123',
        'confirm_password': 'password123'
    })
    client.post('/login', data={'email': 'user@example.com', 'password': 'password123'})

    # Standard user attempting admin route
    res = client.get('/admin')
    assert res.status_code == 403

def test_admin_dashboard_and_management(client):
    """Test admin login, dashboard view, destination CRUD, and user management."""
    with app.app_context():
        admin = User(name='Super Admin', email='admin@example.com', is_admin=True)
        admin.set_password('AdminPass123!')
        
        regular_user = User(name='Member User', email='member@example.com', is_admin=False)
        regular_user.set_password('UserPass123!')
        
        db.session.add(admin)
        db.session.add(regular_user)
        db.session.commit()
        reg_id = regular_user.id

    # Log in as admin
    client.post('/login', data={'email': 'admin@example.com', 'password': 'AdminPass123!'})

    # Access Admin Dashboard
    res = client.get('/admin')
    assert res.status_code == 200
    assert b'Administrator Control Panel' in res.data

    # Manage Destinations (Add new destination)
    res = client.post('/admin/destinations', data={
        'name': 'Kyoto',
        'state': 'Kansai',
        'category': 'Culture',
        'budget_level': 'Moderate',
        'description': 'Ancient cultural capital of Japan with shrines.',
        'tags': 'culture temples history'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'Kyoto' in res.data

    # Toggle admin status of another user
    res = client.post(f'/admin/users/toggle_admin/{reg_id}', follow_redirects=True)
    assert res.status_code == 200
    assert b'Admin privileges granted' in res.data


def test_community_post_deletion(client):
    """Test user can delete their own post, but unauthorized user cannot."""
    # Register Author
    client.post('/register', data={'name': 'Author User', 'email': 'author@example.com', 'password': 'password123', 'confirm_password': 'password123'})
    client.post('/login', data={'email': 'author@example.com', 'password': 'password123'})
    
    # Create Post
    client.post('/community', data={'caption': 'Deleting soon post', 'location_name': 'Goa'}, follow_redirects=True)
    
    with app.app_context():
        post = Post.query.filter_by(caption='Deleting soon post').first()
        assert post is not None
        post_id = post.id

    # Register Stranger User
    client.get('/logout')
    client.post('/register', data={'name': 'Stranger User', 'email': 'stranger@example.com', 'password': 'password123', 'confirm_password': 'password123'})
    client.post('/login', data={'email': 'stranger@example.com', 'password': 'password123'})

    # Stranger tries to delete Author's post -> should receive 403 Forbidden
    res = client.post(f'/community/delete/{post_id}')
    assert res.status_code == 403

    # Log in back as Author and delete post -> should succeed
    client.get('/logout')
    client.post('/login', data={'email': 'author@example.com', 'password': 'password123'})
    res = client.post(f'/community/delete/{post_id}', follow_redirects=True)
    assert res.status_code == 200
    assert b'Post deleted successfully' in res.data


def test_gemini_wrapper_offline():
    """Test Gemini wrapper returns realistic travel advice in offline fallback mode."""
    reply = ask_travel_gemini("Suggest a 3-day itinerary for Goa")
    assert reply is not None
    assert len(reply) > 20
    assert "Itinerary" in reply or "Day" in reply or "TravelAI" in reply


def test_api_chat_endpoint_valid(client):
    """Test /api/chat endpoint with valid JSON prompt."""
    res = client.post('/api/chat', json={
        'message': 'What should I pack for a mountain trek?',
        'history': []
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert 'reply' in data
    assert len(data['reply']) > 0


def test_api_chat_endpoint_empty_message(client):
    """Test /api/chat endpoint rejects empty message."""
    res = client.post('/api/chat', json={'message': '   '})
    assert res.status_code == 400
    data = res.get_json()
    assert data['success'] is False


def test_api_chat_endpoint_non_json(client):
    """Test /api/chat endpoint rejects non-JSON request."""
    res = client.post('/api/chat', data='message=hello')
    assert res.status_code == 400


def test_gemini_503_retry_and_fallback(monkeypatch):
    """Test that HTTP 503 triggers 3 retries with [2, 4, 8] backoff and falls back gracefully."""
    from unittest.mock import MagicMock
    from api.gemini import _ask_via_rest_api

    sleep_calls = []
    monkeypatch.setattr('time.sleep', lambda s: sleep_calls.append(s))
    
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_response.text = '{"error": {"code": 503, "message": "High demand"}}'
    
    post_calls = []
    def mock_post(*args, **kwargs):
        post_calls.append(args)
        return mock_response
        
    monkeypatch.setattr('requests.post', mock_post)

    reply = _ask_via_rest_api('fake_key', 'gemini-3.8-flash', 'Plan my trip')
    assert reply is None
    assert sleep_calls == [2, 4, 8]
    assert len(post_calls) == 4  # 1 initial + 3 retries


