import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default_travel_ai_secret_key_2026')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URI', f'sqlite:///{os.path.join(BASE_DIR, "travel_ai.db")}')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    OPENWEATHER_API_KEY = os.environ.get('OPENWEATHER_API_KEY', '')
    GEOAPIFY_API_KEY = os.environ.get('GEOAPIFY_API_KEY', '')
    
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
