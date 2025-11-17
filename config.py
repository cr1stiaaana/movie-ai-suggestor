import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration"""
    TMDB_API_KEY = os.getenv('TMDB_API_KEY')
    TMDB_BASE_URL = 'https://api.themoviedb.org/3'
    TMDB_IMAGE_BASE_URL = 'https://image.tmdb.org/t/p/w500'
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    CACHE_TTL = 86400  # 24 hours in seconds
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]  # Exponential backoff in seconds
    LOG_FILE = 'app.log'
