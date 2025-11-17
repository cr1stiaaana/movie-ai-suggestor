from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
from config import Config
from tmdb_client import TMDbClient
from csv_importer import CSVImporter
from recommendation_engine import RecommendationEngine
import traceback

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(
    filename=Config.LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize services
tmdb_client = TMDbClient(Config.TMDB_API_KEY)
csv_importer = CSVImporter(tmdb_client)
recommendation_engine = RecommendationEngine(tmdb_client)

# In-memory storage for user movie history (in production, use a database)
user_movies = []


@app.route('/api/upload-csv', methods=['POST'])
def upload_csv():
    """Handle CSV file upload and import movies"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.endswith('.csv'):
            return jsonify({'error': 'File must be a CSV'}), 400
        
        # Read file content
        file_content = file.read().decode('utf-8')
        
        # Import movies
        result = csv_importer.import_csv(file_content)
        
        if result['success']:
            # Add imported movies to user history
            user_movies.extend(result['movies'])
            
            return jsonify({
                'success': True,
                'count': result['count'],
                'message': f"Successfully imported {result['count']} movies",
                'errors': result.get('errors', [])
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Import failed'),
                'errors': result.get('errors', [])
            }), 400
            
    except Exception as e:
        logger.error(f"Error in upload_csv: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/add-movie', methods=['POST'])
def add_movie():
    """Add a movie manually by searching TMDb"""
    try:
        data = request.json
        logger.info(f"Received data: {data}")
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # If user is confirming a specific movie (has tmdb_id)
        if 'tmdb_id' in data:
            tmdb_id = data['tmdb_id']
            rating = data.get('rating')
            watch_date = data.get('watch_date')
            
            # Get full movie details
            movie_details = tmdb_client.get_movie_details(tmdb_id)
            
            if movie_details:
                movie_entry = {
                    'tmdb_id': tmdb_id,
                    'title': movie_details['title'],
                    'year': movie_details['year'],
                    'genres': movie_details['genres'],
                    'rating': rating,
                    'watch_date': watch_date,
                    'poster_path': movie_details.get('poster_path'),
                    'overview': movie_details.get('overview')
                }
                
                user_movies.append(movie_entry)
                
                return jsonify({
                    'success': True,
                    'message': f"Added '{movie_details['title']}' to your collection",
                    'movie': movie_entry
                }), 200
            else:
                return jsonify({'error': 'Failed to fetch movie details'}), 500
        
        # Otherwise, search for movies by title
        if 'title' not in data:
            return jsonify({'error': 'Movie title is required'}), 400
        
        title = data['title']
        year = data.get('year')
        
        # Search TMDb for the movie
        search_results = tmdb_client.search_movie(title, year)
        
        if not search_results:
            return jsonify({
                'error': 'Movie not found',
                'message': f"No results found for '{title}'"
            }), 404
        
        # Return search results for user to select
        return jsonify({
            'matches': search_results[:5]  # Return top 5 matches
        }), 200
        
    except Exception as e:
        logger.error(f"Error in add_movie: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/recommendations', methods=['GET'])
def get_recommendations():
    """Generate personalized movie recommendations"""
    try:
        if len(user_movies) < 5:
            return jsonify({
                'error': 'Insufficient data',
                'message': f"You need at least 5 rated movies to get recommendations. You have {len(user_movies)}."
            }), 400
        
        # Generate recommendations
        recommendations = recommendation_engine.generate_recommendations(user_movies)
        
        return jsonify({
            'success': True,
            'recommendations': recommendations,
            'count': len(recommendations)
        }), 200
        
    except Exception as e:
        logger.error(f"Error in get_recommendations: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/movie/<int:tmdb_id>', methods=['GET'])
def get_movie_details(tmdb_id):
    """Get detailed information about a specific movie"""
    try:
        movie_details = tmdb_client.get_movie_details(tmdb_id)
        
        if movie_details:
            return jsonify(movie_details), 200
        else:
            return jsonify({'error': 'Movie not found'}), 404
            
    except Exception as e:
        logger.error(f"Error in get_movie_details: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/movies', methods=['GET'])
def get_user_movies():
    """Get all movies in user's collection"""
    try:
        return jsonify({
            'movies': user_movies,
            'count': len(user_movies)
        }), 200
    except Exception as e:
        logger.error(f"Error in get_user_movies: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': 'Internal server error'}), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
