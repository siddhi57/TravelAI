import os
import requests
from config import Config

OPENWEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5"

def get_current_weather(city_name):
    """
    Fetches current weather for a given city from OpenWeatherMap API.
    Returns a dictionary with weather details or fallback mock data on error/missing key.
    """
    api_key = Config.OPENWEATHER_API_KEY or os.getenv('OPENWEATHER_API_KEY', '')
    
    if api_key:
        try:
            url = f"{OPENWEATHER_BASE_URL}/weather"
            params = {
                'q': city_name,
                'appid': api_key,
                'units': 'metric'
            }
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                return {
                    'city': data.get('name', city_name),
                    'country': data.get('sys', {}).get('country', ''),
                    'temp': round(data.get('main', {}).get('temp', 24)),
                    'feels_like': round(data.get('main', {}).get('feels_like', 25)),
                    'humidity': data.get('main', {}).get('humidity', 65),
                    'wind_speed': round(data.get('wind', {}).get('speed', 4.2), 1),
                    'condition': data['weather'][0]['description'].capitalize() if data.get('weather') else 'Clear sky',
                    'icon': data['weather'][0]['icon'] if data.get('weather') else '01d',
                    'is_fallback': False,
                    'message': 'Live OpenWeatherMap data'
                }
        except Exception as e:
            # Fallback on network failure or timeout
            pass

    # Fallback mock weather data
    city_clean = city_name.title() if city_name else 'Destination'
    return {
        'city': city_clean,
        'country': 'Travel',
        'temp': 24,
        'feels_like': 25,
        'humidity': 60,
        'wind_speed': 3.5,
        'condition': 'Partly cloudy (Simulated)',
        'icon': '02d',
        'is_fallback': True,
        'message': 'Using offline simulated weather data. Add OPENWEATHER_API_KEY in .env for live weather.'
    }

def get_weather_forecast(city_name):
    """
    Fetches 5-day weather forecast for a given city from OpenWeatherMap API.
    Returns a list of daily forecast dictionaries or fallback data on failure.
    """
    api_key = Config.OPENWEATHER_API_KEY or os.getenv('OPENWEATHER_API_KEY', '')
    
    if api_key:
        try:
            url = f"{OPENWEATHER_BASE_URL}/forecast"
            params = {
                'q': city_name,
                'appid': api_key,
                'units': 'metric'
            }
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                forecast_items = []
                # Pick every 8th item (sampled every ~24 hours)
                list_data = data.get('list', [])
                for i in range(0, min(len(list_data), 40), 8):
                    item = list_data[i]
                    forecast_items.append({
                        'date': item.get('dt_txt', '').split(' ')[0],
                        'temp': round(item.get('main', {}).get('temp', 24)),
                        'condition': item['weather'][0]['description'].capitalize() if item.get('weather') else 'Sunny',
                        'icon': item['weather'][0]['icon'] if item.get('weather') else '01d'
                    })
                return {
                    'forecast': forecast_items,
                    'is_fallback': False
                }
        except Exception:
            pass

    # Simulated fallback 5-day forecast
    from datetime import datetime, timedelta
    today = datetime.now()
    simulated_forecast = []
    conditions = [
        ('Sunny', '01d', 26),
        ('Partly Cloudy', '02d', 24),
        ('Light Rain', '10d', 22),
        ('Clear Sky', '01d', 25),
        ('Pleasant Breeze', '03d', 23)
    ]
    for i in range(5):
        day_date = (today + timedelta(days=i)).strftime('%Y-%m-%d')
        cond, icon, temp = conditions[i % len(conditions)]
        simulated_forecast.append({
            'date': day_date,
            'temp': temp,
            'condition': cond,
            'icon': icon
        })
        
    return {
        'forecast': simulated_forecast,
        'is_fallback': True
    }
