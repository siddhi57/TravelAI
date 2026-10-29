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
    """Test TF-IDF recommender engine standalone with legacy and budget ranges."""
    recommender = DestinationRecommender()
    results = recommender.recommend(
        budget_level='Moderate',
        category='Beach',
        interests=['beach', 'nightlife'],
        top_n=5
    )
    assert len(results) > 0
    assert 'name' in results[0]

    # Test budget range matching
    results_range = recommender.recommend(
        budget_level='6,000 - 15,000',
        category='Beach',
        interests=['beach'],
        top_n=5
    )
    assert len(results_range) > 0
    assert 'name' in results_range[0]

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
    assert b'chatbotContainer' in res.data
    assert b'chatbot.js' in res.data
    
    res = client.get('/recommendations')
    assert res.status_code == 200
    
    res = client.get('/hotels?destination=Goa')
    assert res.status_code == 200
    
    res = client.get('/weather?destination=Goa')
    assert res.status_code == 200
    
    res = client.get('/attractions?destination=Goa')
    assert res.status_code == 200
    assert b'Tourist Attraction' in res.data
    
    res = client.get('/tourist-attractions?destination=Goa')
    assert res.status_code == 200
    assert b'Tourist Attraction' in res.data
    
    res = client.get('/itinerary')
    assert res.status_code == 200

    res = client.get('/community?page=1')
    assert res.status_code == 200

def test_auth_workflow(client):
    """Test user registration, login, profile, and password complexity checks."""
    # Register with short password should fail
    res = client.post('/register', data={
        'name': 'Test Traveler',
        'email': 'traveler@example.com',
        'password': 'short',
        'confirm_password': 'short'
    }, follow_redirects=True)
    assert b'Password must be at least 8 characters long' in res.data

    # Missing alphabet letter
    res = client.post('/register', data={
        'name': 'Test Traveler',
        'email': 'traveler@example.com',
        'password': '12345678!',
        'confirm_password': '12345678!'
    }, follow_redirects=True)
    assert b'Password must contain at least one alphabet letter.' in res.data

    # Missing digit
    res = client.post('/register', data={
        'name': 'Test Traveler',
        'email': 'traveler@example.com',
        'password': 'TravelPass!',
        'confirm_password': 'TravelPass!'
    }, follow_redirects=True)
    assert b'Password must contain at least one digit (number).' in res.data

    # Missing special character
    res = client.post('/register', data={
        'name': 'Test Traveler',
        'email': 'traveler@example.com',
        'password': 'TravelPass123',
        'confirm_password': 'TravelPass123'
    }, follow_redirects=True)
    assert b'Password must contain at least one special character' in res.data

    # Valid Registration
    res = client.post('/register', data={
        'name': 'Test Traveler',
        'email': 'traveler@example.com',
        'password': 'TravelPass123!',
        'confirm_password': 'TravelPass123!'
    }, follow_redirects=True)
    assert res.status_code == 200
    
    # Login
    res = client.post('/login', data={
        'email': 'traveler@example.com',
        'password': 'TravelPass123!'
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
        'password': 'TravelPass123!',
        'confirm_password': 'TravelPass123!'
    })
    client.post('/login', data={'email': 'user@example.com', 'password': 'TravelPass123!'})

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

        assistant_admin = User(name='Co Admin', email='coadmin@example.com', is_admin=True)
        assistant_admin.set_password('AdminPass123!')
        
        db.session.add(admin)
        db.session.add(regular_user)
        db.session.add(assistant_admin)
        db.session.commit()
        reg_id = regular_user.id
        coadmin_id = assistant_admin.id

    # Log in as admin
    client.post('/login', data={'email': 'admin@example.com', 'password': 'AdminPass123!'})

    # Access Admin Dashboard (Chatbot popup should be omitted)
    res = client.get('/admin')
    assert res.status_code == 200
    assert b'Administrator Control Panel' in res.data
    assert b'chatbotContainer' not in res.data
    assert b'chatbot.js' not in res.data

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

    # Verify Promote to Admin is absent and chatbot is omitted in admin users view
    res = client.get('/admin/users')
    assert res.status_code == 200
    assert b'Promote to Admin' not in res.data
    assert b'chatbotContainer' not in res.data
    assert b'chatbot.js' not in res.data

    # Attempting to promote standard user to admin should be blocked
    res = client.post(f'/admin/users/toggle_admin/{reg_id}', follow_redirects=True)
    assert res.status_code == 200
    assert b'Promoting standard users to admin is disabled' in res.data

    # Demoting an existing admin should succeed
    res = client.post(f'/admin/users/toggle_admin/{coadmin_id}', follow_redirects=True)
    assert res.status_code == 200
    assert b'Admin privileges revoked' in res.data


def test_admin_photo_moderation(client):
    """Test admin can view uploaded post photos in the moderation queue."""
    with app.app_context():
        admin = User(name='Admin Mod', email='adminmod@example.com', is_admin=True)
        admin.set_password('AdminPass123!')
        db.session.add(admin)
        db.session.commit()
        
        post = Post(
            user_id=admin.id,
            caption="Check out this view!",
            image_path="test_moderation_photo.jpg",
            location_name="Goa"
        )
        db.session.add(post)
        db.session.commit()
        post_id = post.id

    # Log in as admin
    client.post('/login', data={'email': 'adminmod@example.com', 'password': 'AdminPass123!'})

    # Access moderation queue
    res = client.get('/admin/posts')
    assert res.status_code == 200
    assert b'test_moderation_photo.jpg' in res.data
    assert f'photoModal{post_id}'.encode() in res.data
    assert b'Photo Moderation' in res.data


def test_community_post_deletion(client):
    """Test user can delete their own post, but unauthorized user cannot."""
    # Register Author
    client.post('/register', data={'name': 'Author User', 'email': 'author@example.com', 'password': 'TravelPass123!', 'confirm_password': 'TravelPass123!'})
    client.post('/login', data={'email': 'author@example.com', 'password': 'TravelPass123!'})
    
    # Create Post
    client.post('/community', data={'caption': 'Deleting soon post', 'location_name': 'Goa'}, follow_redirects=True)
    
    with app.app_context():
        post = Post.query.filter_by(caption='Deleting soon post').first()
        assert post is not None
        post_id = post.id

    # Register Stranger User
    client.get('/logout')
    client.post('/register', data={'name': 'Stranger User', 'email': 'stranger@example.com', 'password': 'TravelPass123!', 'confirm_password': 'TravelPass123!'})
    client.post('/login', data={'email': 'stranger@example.com', 'password': 'TravelPass123!'})

    # Stranger tries to delete Author's post -> should receive 403 Forbidden
    res = client.post(f'/community/delete/{post_id}')
    assert res.status_code == 403

    # Log in back as Author and delete post -> should succeed
    client.get('/logout')
    client.post('/login', data={'email': 'author@example.com', 'password': 'TravelPass123!'})
    res = client.post(f'/community/delete/{post_id}', follow_redirects=True)
    assert res.status_code == 200
    assert b'Post deleted successfully' in res.data


def test_gemini_wrapper_offline():
    """Test Gemini wrapper returns realistic travel advice in offline fallback mode."""
    reply = ask_travel_gemini("Suggest a 3-day itinerary for Goa")
    assert reply is not None
    assert len(reply) > 20
    assert "Itinerary" in reply or "Day" in reply or "TravelAI" in reply


def test_chatbot_dynamic_itinerary_days():
    """Test that chatbot generates the exact number of itinerary days requested."""
    # 5 days
    reply_5 = ask_travel_gemini("Suggest a 5-day itinerary for Paris")
    assert reply_5.count("* **Day ") == 5
    assert "* **Day 1:" in reply_5
    assert "* **Day 5:" in reply_5
    assert "* **Day 6:" not in reply_5
    assert "Paris" in reply_5

    # 7 days
    reply_7 = ask_travel_gemini("7 days plan for Goa")
    assert reply_7.count("* **Day ") == 7
    assert "* **Day 7:" in reply_7
    assert "* **Day 8:" not in reply_7
    assert "Goa" in reply_7

    # 4 days
    reply_4 = ask_travel_gemini("give me a 4-day trip plan for Manali")
    assert reply_4.count("* **Day ") == 4
    assert "* **Day 4:" in reply_4
    assert "* **Day 5:" not in reply_4
    assert "Manali" in reply_4

    # 1 day
    reply_1 = ask_travel_gemini("1 day itinerary for Jaipur")
    assert reply_1.count("* **Day ") == 1
    assert "* **Day 1:" in reply_1
    assert "* **Day 2:" not in reply_1
    assert "Jaipur" in reply_1


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

def test_itinerary_generation_and_editable_interface(client):
    """Test generating day-by-day itinerary and verify interactive editing controls."""
    # Initial GET
    res = client.get('/itinerary')
    assert res.status_code == 200
    assert b'AI Day-by-Day Itinerary Generator' in res.data
    
    # POST to generate a 3-day itinerary with custom budget range
    res = client.post('/itinerary', data={
        'destination': 'Jaipur',
        'days': 3,
        'budget': '6,000 - 15,000'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'3-Day Plan for Jaipur' in res.data
    
    # Verify editable interface elements and modals are rendered
    assert b'initialItineraryData' in res.data
    assert b'itineraryScheduleWrapper' in res.data
    assert b'editActivityModal' in res.data
    assert b'addActivityModal' in res.data
    assert b'Add Day' in res.data
    assert b'Export Text' not in res.data
    assert b'Print / PDF' not in res.data

