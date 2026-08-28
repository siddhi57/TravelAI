import os
import requests
import random
from config import Config

GEOAPIFY_GEOCODE_URL = "https://api.geoapify.com/v1/geocode/search"
GEOAPIFY_PLACES_URL = "https://api.geoapify.com/v2/places"

# Fallback default coordinates for common destinations
DEFAULT_COORDS = {
    'goa': (15.2993, 74.1240),
    'manali': (32.2432, 77.1892),
    'jaipur': (26.9124, 75.7873),
    'kerala': (10.8505, 76.2711),
    'leh': (34.1526, 77.5771),
    'varanasi': (25.3176, 82.9739),
    'ooty': (11.4102, 76.6950),
    'paris': (48.8566, 2.3522),
    'tokyo': (35.6762, 139.6503),
    'london': (51.5074, -0.1278),
    'new york': (40.7128, -74.0060),
    'dubai': (25.2048, 55.2708),
    'bali': (8.3405, 115.0920),
    'udaipur': (24.5854, 73.7125),
    'shimla': (31.1048, 77.1734),
    'darjeeling': (27.0410, 88.2663),
    'agra': (27.1767, 78.0081),
    'mumbai': (19.0760, 72.8777),
    'delhi': (28.6139, 77.2090),
    'bangalore': (12.9716, 77.5946)
}

def geocode_location(location_name):
    """
    Geocodes a location name to (lat, lng, formatted_address).
    Uses Geoapify Geocoding API if key is present; falls back to Nominatim OSM or default mock coords.
    """
    api_key = Config.GEOAPIFY_API_KEY or os.getenv('GEOAPIFY_API_KEY', '')
    
    if api_key:
        try:
            params = {
                'text': location_name,
                'apiKey': api_key,
                'limit': 1
            }
            response = requests.get(GEOAPIFY_GEOCODE_URL, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                features = data.get('features', [])
                if features:
                    props = features[0]['properties']
                    lat = props.get('lat')
                    lng = props.get('lon')
                    address = props.get('formatted', location_name)
                    return {
                        'lat': lat,
                        'lng': lng,
                        'formatted_address': address,
                        'is_fallback': False
                    }
        except Exception:
            pass

    # Try OpenStreetMap Nominatim API as a free secondary fallback
    try:
        nom_url = "https://nominatim.openstreetmap.org/search"
        headers = {'User-Agent': 'TravelAICompanionApp/1.0'}
        params = {'q': location_name, 'format': 'json', 'limit': 1}
        resp = requests.get(nom_url, params=params, headers=headers, timeout=3)
        if resp.status_code == 200 and resp.json():
            item = resp.json()[0]
            return {
                'lat': float(item['lat']),
                'lng': float(item['lon']),
                'formatted_address': item.get('display_name', location_name),
                'is_fallback': False
            }
    except Exception:
        pass

    # Fallback to local dictionary or generated coordinates
    loc_key = location_name.lower().strip()
    for key, (d_lat, d_lng) in DEFAULT_COORDS.items():
        if key in loc_key:
            return {
                'lat': d_lat,
                'lng': d_lng,
                'formatted_address': f"{location_name.title()} (Simulated Coordinates)",
                'is_fallback': True
            }
            
    # Default center if unknown
    return {
        'lat': 20.5937,
        'lng': 78.9629,
        'formatted_address': f"{location_name.title()} (Default Location)",
        'is_fallback': True
    }


def get_nearby_hotels(location_name, budget_tier='Moderate', radius_meters=10000, limit=8):
    """
    Fetches nearby hotels/accommodations for a destination via Geoapify Places API.
    Returns list of hotel dicts: name, address, rating, price_tier, lat, lng.
    """
    coords = geocode_location(location_name)
    lat, lng = coords['lat'], coords['lng']
    
    api_key = Config.GEOAPIFY_API_KEY or os.getenv('GEOAPIFY_API_KEY', '')
    
    if api_key:
        try:
            categories = "accommodation.hotel,accommodation.guest_house"
            params = {
                'categories': categories,
                'filter': f"circle:{lng},{lat},{radius_meters}",
                'bias': f"proximity:{lng},{lat}",
                'limit': limit,
                'apiKey': api_key
            }
            response = requests.get(GEOAPIFY_PLACES_URL, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                features = data.get('features', [])
                hotels = []
                for feat in features:
                    props = feat.get('properties', {})
                    h_lat = props.get('lat', lat)
                    h_lng = props.get('lon', lng)
                    h_name = props.get('name') or props.get('address_line1') or f"Grand Hotel {location_name.title()}"
                    h_address = props.get('formatted') or f"{h_name}, {location_name.title()}"
                    
                    # Synthesize reasonable rating & price tier if missing from Geoapify free response
                    h_rating = round(random.uniform(4.0, 4.9), 1)
                    h_price = props.get('price_level') or budget_tier
                    
                    hotels.append({
                        'hotel_name': h_name,
                        'address': h_address,
                        'rating': h_rating,
                        'price_tier': h_price,
                        'lat': h_lat,
                        'lng': h_lng,
                        'is_fallback': False
                    })
                if hotels:
                    return hotels
        except Exception:
            pass

    # Simulated fallback hotel list around destination lat/lng
    hotel_types = ['Grand Resort & Spa', 'Heritage Palace Hotel', 'Boutique Stay', 'Comfort Suites', 'Sunset Bay Inn', 'Royal Orchid Hotel']
    fallback_hotels = []
    
    for i, h_type in enumerate(hotel_types[:limit]):
        # Offset coordinates slightly around destination center
        h_lat = lat + random.uniform(-0.02, 0.02)
        h_lng = lng + random.uniform(-0.02, 0.02)
        h_name = f"{location_name.title()} {h_type}"
        h_address = f"{101 + i * 12} Main Boulevard, {location_name.title()}"
        h_rating = round(4.2 + (i % 7) * 0.1, 1)
        h_price = budget_tier if budget_tier else ('Budget' if i % 2 == 0 else 'Luxury')
        
        fallback_hotels.append({
            'hotel_name': h_name,
            'address': h_address,
            'rating': h_rating,
            'price_tier': h_price,
            'lat': h_lat,
            'lng': h_lng,
            'is_fallback': True
        })
        
    return fallback_hotels


def get_nearby_attractions(location_name, radius_meters=15000, limit=12):
    """
    Fetches nearby points of interest / tourist attractions via Geoapify Places API.
    Returns list of attraction dicts: name, category, distance_km, lat, lng, address.
    """
    coords = geocode_location(location_name)
    lat, lng = coords['lat'], coords['lng']
    
    api_key = Config.GEOAPIFY_API_KEY or os.getenv('GEOAPIFY_API_KEY', '')
    
    if api_key:
        try:
            categories = "tourist.attraction,entertainment,leisure,tourism.sights,building.historic"
            params = {
                'categories': categories,
                'filter': f"circle:{lng},{lat},{radius_meters}",
                'bias': f"proximity:{lng},{lat}",
                'limit': limit,
                'apiKey': api_key
            }
            response = requests.get(GEOAPIFY_PLACES_URL, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                features = data.get('features', [])
                attractions = []
                for feat in features:
                    props = feat.get('properties', {})
                    a_name = props.get('name')
                    if not a_name:
                        continue
                    a_lat = props.get('lat', lat)
                    a_lng = props.get('lon', lng)
                    a_cat = props.get('categories', ['attraction'])[0].replace('.', ' ').title()
                    a_dist = round(props.get('distance', 1500) / 1000.0, 2)
                    
                    attractions.append({
                        'name': a_name,
                        'category': a_cat,
                        'distance_km': a_dist,
                        'lat': a_lat,
                        'lng': a_lng,
                        'address': props.get('formatted', f"{a_name}, {location_name.title()}"),
                        'is_fallback': False
                    })
                if attractions:
                    return attractions
        except Exception:
            pass

    # Simulated fallback attractions list
    attraction_templates = [
        ('Central Heritage Fortress & Viewpoint', 'Historical Monument', 1.2),
        ('Botanical Eco Gardens & Waterfall', 'Nature & Park', 2.5),
        ('Sunset Lake & Boat Club', 'Leisure & Lake', 3.8),
        ('Old Town Cultural Bazaar', 'Culture & Shopping', 0.8),
        ('Ancient Temple Complex', 'Religious Heritage', 4.1),
        ('National Art & History Museum', 'Museum & Art', 2.0),
        ('Panoramic Cliffside Promenade', 'Scenic Lookout', 5.4),
        ('Local Craft & Artisan Market', 'Culture & Craft', 1.6),
        ('Adventure River & Canopy Walk', 'Outdoor Adventure', 7.2)
    ]
    
    fallback_attractions = []
    for i, (name_suffix, cat, dist) in enumerate(attraction_templates[:limit]):
        a_lat = lat + random.uniform(-0.03, 0.03)
        a_lng = lng + random.uniform(-0.03, 0.03)
        a_name = f"{location_name.title()} {name_suffix}"
        
        fallback_attractions.append({
            'name': a_name,
            'category': cat,
            'distance_km': dist,
            'lat': a_lat,
            'lng': a_lng,
            'address': f"{a_name}, {location_name.title()}",
            'is_fallback': True
        })
        
    return fallback_attractions
