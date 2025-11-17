import csv
import io
import logging
from typing import Dict, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class CSVImporter:
    """Import movies from CSV files (TV Time and Letterboxd formats)"""
    
    def __init__(self, tmdb_client):
        self.tmdb_client = tmdb_client
    
    def import_csv(self, csv_content: str) -> Dict:
        """
        Import movies from CSV content
        Auto-detects format (TV Time or Letterboxd)
        """
        try:
            # Parse CSV
            csv_file = io.StringIO(csv_content)
            reader = csv.DictReader(csv_file)
            
            # Get headers to detect format
            headers = reader.fieldnames
            
            if not headers:
                return {
                    'success': False,
                    'error': 'Invalid CSV file - no headers found'
                }
            
            # Detect format
            csv_format = self._detect_format(headers)
            
            if not csv_format:
                return {
                    'success': False,
                    'error': f'Unsupported CSV format. Expected TV Time or Letterboxd format. Found headers: {", ".join(headers)}'
                }
            
            logger.info(f"Detected CSV format: {csv_format}")
            
            # Parse rows
            rows = list(reader)
            movies_data = []
            errors = []
            
            for idx, row in enumerate(rows, start=2):  # Start at 2 (1 is header)
                try:
                    movie_data = self._parse_row(row, csv_format)
                    if movie_data:
                        movies_data.append(movie_data)
                except Exception as e:
                    errors.append(f"Row {idx}: {str(e)}")
                    logger.warning(f"Error parsing row {idx}: {str(e)}")
            
            if not movies_data:
                return {
                    'success': False,
                    'error': 'No valid movie entries found in CSV',
                    'errors': errors
                }
            
            # Lookup movies on TMDb (parallel requests for performance)
            movies = self._lookup_movies_parallel(movies_data, errors)
            
            return {
                'success': True,
                'count': len(movies),
                'movies': movies,
                'errors': errors if errors else []
            }
            
        except Exception as e:
            logger.error(f"Error importing CSV: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to parse CSV: {str(e)}'
            }
    
    def _detect_format(self, headers: List[str]) -> str:
        """Detect CSV format based on headers"""
        headers_lower = [h.lower().strip() for h in headers]
        
        # TV Time format detection
        tv_time_indicators = ['movie name', 'rating']
        if all(indicator in headers_lower for indicator in tv_time_indicators):
            return 'tv_time'
        
        # Letterboxd format detection
        letterboxd_indicators = ['name', 'year', 'rating']
        if all(indicator in headers_lower for indicator in letterboxd_indicators):
            return 'letterboxd'
        
        return None
    
    def _parse_row(self, row: Dict, csv_format: str) -> Dict:
        """Parse a single CSV row based on format"""
        if csv_format == 'tv_time':
            return self._parse_tv_time_row(row)
        elif csv_format == 'letterboxd':
            return self._parse_letterboxd_row(row)
        return None
    
    def _parse_tv_time_row(self, row: Dict) -> Dict:
        """Parse TV Time format row"""
        title = row.get('Movie Name', '').strip()
        
        if not title:
            raise ValueError("Missing movie title")
        
        # Extract rating (0-5 scale in TV Time)
        rating_str = row.get('Rating', '').strip()
        rating = None
        if rating_str:
            try:
                # Convert 0-5 scale to 0-10 scale
                rating = float(rating_str) * 2
            except ValueError:
                pass
        
        # Extract watch date
        watch_date = row.get('Date', '').strip()
        if watch_date:
            try:
                # Try to parse date
                watch_date = datetime.strptime(watch_date, '%Y-%m-%d').strftime('%Y-%m-%d')
            except ValueError:
                watch_date = None
        
        # Extract year if available
        year = None
        year_str = row.get('Year', '').strip()
        if year_str:
            try:
                year = int(year_str)
            except ValueError:
                pass
        
        return {
            'title': title,
            'year': year,
            'rating': rating,
            'watch_date': watch_date
        }
    
    def _parse_letterboxd_row(self, row: Dict) -> Dict:
        """Parse Letterboxd format row"""
        title = row.get('Name', '').strip()
        
        if not title:
            raise ValueError("Missing movie title")
        
        # Extract year
        year = None
        year_str = row.get('Year', '').strip()
        if year_str:
            try:
                year = int(year_str)
            except ValueError:
                pass
        
        # Extract rating (0-5 scale in Letterboxd, stored as stars)
        rating_str = row.get('Rating', '').strip()
        rating = None
        if rating_str:
            try:
                # Convert 0-5 scale to 0-10 scale
                rating = float(rating_str) * 2
            except ValueError:
                pass
        
        # Extract watch date
        watch_date = row.get('Watched Date', '').strip()
        if watch_date:
            try:
                # Try to parse date
                watch_date = datetime.strptime(watch_date, '%Y-%m-%d').strftime('%Y-%m-%d')
            except ValueError:
                watch_date = None
        
        return {
            'title': title,
            'year': year,
            'rating': rating,
            'watch_date': watch_date
        }
    
    def _lookup_movies_parallel(self, movies_data: List[Dict], errors: List[str]) -> List[Dict]:
        """Lookup movies on TMDb using parallel requests"""
        movies = []
        
        # Use ThreadPoolExecutor for parallel API calls
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Submit all lookup tasks
            future_to_movie = {
                executor.submit(self._lookup_single_movie, movie_data): movie_data
                for movie_data in movies_data
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_movie):
                movie_data = future_to_movie[future]
                try:
                    result = future.result()
                    if result:
                        movies.append(result)
                    else:
                        errors.append(f"Movie not found on TMDb: {movie_data['title']}")
                except Exception as e:
                    errors.append(f"Error looking up '{movie_data['title']}': {str(e)}")
                    logger.error(f"Error in parallel lookup: {str(e)}")
        
        return movies
    
    def _lookup_single_movie(self, movie_data: Dict) -> Dict:
        """Lookup a single movie on TMDb"""
        title = movie_data['title']
        year = movie_data.get('year')
        
        # Search TMDb
        search_results = self.tmdb_client.search_movie(title, year)
        
        if not search_results:
            logger.warning(f"No TMDb results for: {title}")
            return None
        
        # Take the top match
        top_match = search_results[0]
        
        # Get full details
        movie_details = self.tmdb_client.get_movie_details(top_match['tmdb_id'])
        
        if not movie_details:
            return None
        
        # Combine with user data
        return {
            'tmdb_id': movie_details['tmdb_id'],
            'title': movie_details['title'],
            'year': movie_details['year'],
            'genres': movie_details['genres'],
            'rating': movie_data.get('rating'),
            'watch_date': movie_data.get('watch_date'),
            'poster_path': movie_details.get('poster_path'),
            'overview': movie_details.get('overview'),
            'tmdb_rating': movie_details.get('rating'),
            'popularity': movie_details.get('popularity')
        }
