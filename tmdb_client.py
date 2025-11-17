import requests
import time
import logging
from typing import Optional, List, Dict
from config import Config

logger = logging.getLogger(__name__)


class TMDbClient:
    """Client for interacting with The Movie Database (TMDb) API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = Config.TMDB_BASE_URL
        self.image_base_url = Config.TMDB_IMAGE_BASE_URL
        self.cache = {}  # In-memory cache with TTL
        self.cache_timestamps = {}
        
        if not self.api_key:
            raise ValueError("TMDb API key is required")
    
    def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make a request to TMDb API with retry logic and caching"""
        # Check cache first
        cache_key = f"{endpoint}:{str(params)}"
        if cache_key in self.cache:
            # Check if cache is still valid (TTL)
            if time.time() - self.cache_timestamps[cache_key] < Config.CACHE_TTL:
                logger.info(f"Cache hit for {endpoint}")
                return self.cache[cache_key]
            else:
                # Cache expired, remove it
                del self.cache[cache_key]
                del self.cache_timestamps[cache_key]
        
        url = f"{self.base_url}/{endpoint}"
        
        if params is None:
            params = {}
        
        params['api_key'] = self.api_key
        
        # Retry logic with exponential backoff
        for attempt in range(Config.MAX_RETRIES):
            try:
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    # Cache the successful response
                    self.cache[cache_key] = data
                    self.cache_timestamps[cache_key] = time.time()
                    return data
                elif response.status_code == 401:
                    logger.error("TMDb API authentication failed - invalid API key")
                    return None
                elif response.status_code == 429:
                    logger.warning("TMDb API rate limit exceeded")
                    if attempt < Config.MAX_RETRIES - 1:
                        time.sleep(Config.RETRY_DELAYS[attempt])
                        continue
                    return None
                elif response.status_code == 404:
                    logger.info(f"Resource not found: {endpoint}")
                    return None
                else:
                    logger.error(f"TMDb API error: {response.status_code}")
                    if attempt < Config.MAX_RETRIES - 1:
                        time.sleep(Config.RETRY_DELAYS[attempt])
                        continue
                    return None
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Request timeout (attempt {attempt + 1}/{Config.MAX_RETRIES})")
                if attempt < Config.MAX_RETRIES - 1:
                    time.sleep(Config.RETRY_DELAYS[attempt])
                    continue
                return None
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error: {str(e)}")
                if attempt < Config.MAX_RETRIES - 1:
                    time.sleep(Config.RETRY_DELAYS[attempt])
                    continue
                return None
        
        return None
    
    def search_movie(self, title: str, year: Optional[int] = None) -> List[Dict]:
        """
        Search for movies by title
        Returns a list of movie matches ranked by relevance
        """
        params = {'query': title}
        
        if year:
            params['year'] = year
        
        data = self._make_request('search/movie', params)
        
        if not data or 'results' not in data:
            return []
        
        results = data['results']
        
        # Rank results by popularity and release year proximity
        if year:
            # Boost movies with matching year
            for movie in results:
                release_year = None
                if movie.get('release_date'):
                    try:
                        release_year = int(movie['release_date'][:4])
                    except (ValueError, IndexError):
                        pass
                
                # Calculate relevance score
                popularity_score = movie.get('popularity', 0)
                year_match_bonus = 100 if release_year == year else 0
                movie['relevance_score'] = popularity_score + year_match_bonus
            
            results.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        else:
            # Sort by popularity only
            results.sort(key=lambda x: x.get('popularity', 0), reverse=True)
        
        # Format results
        formatted_results = []
        for movie in results[:10]:  # Return top 10
            release_year = None
            if movie.get('release_date'):
                try:
                    release_year = int(movie['release_date'][:4])
                except (ValueError, IndexError):
                    pass
            
            formatted_results.append({
                'tmdb_id': movie['id'],
                'title': movie['title'],
                'year': release_year,
                'overview': movie.get('overview', ''),
                'poster_path': f"{self.image_base_url}{movie['poster_path']}" if movie.get('poster_path') else None,
                'popularity': movie.get('popularity', 0)
            })
        
        return formatted_results
    
    def get_movie_details(self, tmdb_id: int) -> Optional[Dict]:
        """
        Get detailed information about a specific movie
        Includes cast, director, runtime, genres, synopsis, poster
        """
        # Get basic movie details
        movie_data = self._make_request(f'movie/{tmdb_id}')
        
        if not movie_data:
            return None
        
        # Get credits (cast and crew)
        credits_data = self._make_request(f'movie/{tmdb_id}/credits')
        
        # Extract cast (top 10)
        cast = []
        if credits_data and 'cast' in credits_data:
            for actor in credits_data['cast'][:10]:
                cast.append({
                    'name': actor['name'],
                    'character': actor.get('character', '')
                })
        
        # Extract director
        director = None
        if credits_data and 'crew' in credits_data:
            for crew_member in credits_data['crew']:
                if crew_member.get('job') == 'Director':
                    director = crew_member['name']
                    break
        
        # Extract genres
        genres = [genre['name'] for genre in movie_data.get('genres', [])]
        
        # Extract release year
        release_year = None
        if movie_data.get('release_date'):
            try:
                release_year = int(movie_data['release_date'][:4])
            except (ValueError, IndexError):
                pass
        
        return {
            'tmdb_id': movie_data['id'],
            'title': movie_data['title'],
            'year': release_year,
            'genres': genres,
            'overview': movie_data.get('overview', ''),
            'runtime': movie_data.get('runtime'),
            'rating': movie_data.get('vote_average'),
            'poster_path': f"{self.image_base_url}{movie_data['poster_path']}" if movie_data.get('poster_path') else None,
            'backdrop_path': f"{self.image_base_url}{movie_data['backdrop_path']}" if movie_data.get('backdrop_path') else None,
            'cast': cast,
            'director': director,
            'popularity': movie_data.get('popularity', 0)
        }
    
    def get_popular_movies(self, limit: int = 1000) -> List[Dict]:
        """
        Get popular movies for recommendation candidate pool
        """
        all_movies = []
        pages_needed = (limit // 20) + 1  # TMDb returns 20 results per page
        
        for page in range(1, min(pages_needed + 1, 51)):  # TMDb limits to 500 pages
            data = self._make_request('movie/popular', {'page': page})
            
            if not data or 'results' not in data:
                break
            
            for movie in data['results']:
                release_year = None
                if movie.get('release_date'):
                    try:
                        release_year = int(movie['release_date'][:4])
                    except (ValueError, IndexError):
                        pass
                
                # Get genre names
                genre_ids = movie.get('genre_ids', [])
                
                all_movies.append({
                    'tmdb_id': movie['id'],
                    'title': movie['title'],
                    'year': release_year,
                    'genre_ids': genre_ids,
                    'overview': movie.get('overview', ''),
                    'rating': movie.get('vote_average', 0),
                    'popularity': movie.get('popularity', 0),
                    'poster_path': f"{self.image_base_url}{movie['poster_path']}" if movie.get('poster_path') else None
                })
                
                if len(all_movies) >= limit:
                    return all_movies
        
        return all_movies
