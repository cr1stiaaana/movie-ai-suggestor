import numpy as np
import logging
from typing import List, Dict
from collections import Counter
from datetime import datetime

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """ML-based movie recommendation engine using content-based filtering"""
    
    def __init__(self, tmdb_client):
        self.tmdb_client = tmdb_client
        self.genre_map = {
            28: 'Action', 12: 'Adventure', 16: 'Animation', 35: 'Comedy',
            80: 'Crime', 99: 'Documentary', 18: 'Drama', 10751: 'Family',
            14: 'Fantasy', 36: 'History', 27: 'Horror', 10402: 'Music',
            9648: 'Mystery', 10749: 'Romance', 878: 'Science Fiction',
            10770: 'TV Movie', 53: 'Thriller', 10752: 'War', 37: 'Western'
        }
    
    def generate_recommendations(self, user_movies: List[Dict], num_recommendations: int = 10) -> List[Dict]:
        """
        Generate personalized movie recommendations
        Requires minimum 5 rated movies
        """
        if len(user_movies) < 5:
            raise ValueError(f"Insufficient data: need at least 5 movies, have {len(user_movies)}")
        
        logger.info(f"Generating recommendations for {len(user_movies)} movies")
        
        # Build user profile
        user_profile = self._build_user_profile(user_movies)
        
        logger.info(f"User profile: {user_profile}")
        
        # Get candidate movies from TMDb
        candidates = self._get_candidate_movies(user_movies)
        
        logger.info(f"Found {len(candidates)} candidate movies")
        
        # Score candidates
        scored_candidates = self._score_candidates(candidates, user_profile)
        
        # Sort by score and return top N
        scored_candidates.sort(key=lambda x: x['score'], reverse=True)
        
        recommendations = scored_candidates[:num_recommendations]
        
        # Enrich with full details
        enriched_recommendations = []
        for rec in recommendations:
            details = self.tmdb_client.get_movie_details(rec['tmdb_id'])
            if details:
                enriched_recommendations.append({
                    **details,
                    'match_score': rec['score'],
                    'reasoning': rec['reasoning']
                })
        
        return enriched_recommendations
    
    def _build_user_profile(self, user_movies: List[Dict]) -> Dict:
        """Analyze user's viewing history to build preference profile"""
        # Filter highly-rated movies (rating >= 4.0 on 0-10 scale)
        highly_rated = [m for m in user_movies if m.get('rating') and m['rating'] >= 4.0]
        
        if not highly_rated:
            # If no highly rated movies, use all movies
            highly_rated = user_movies
        
        # Calculate genre preferences
        genre_counts = Counter()
        for movie in highly_rated:
            for genre in movie.get('genres', []):
                genre_counts[genre] += 1
        
        # Normalize genre preferences
        total_genres = sum(genre_counts.values())
        genre_preferences = {
            genre: count / total_genres
            for genre, count in genre_counts.items()
        } if total_genres > 0 else {}
        
        # Calculate rating statistics
        ratings = [m['rating'] for m in user_movies if m.get('rating')]
        avg_rating = np.mean(ratings) if ratings else 5.0
        rating_std = np.std(ratings) if len(ratings) > 1 else 1.0
        
        # Identify preferred decades
        decades = []
        for movie in highly_rated:
            if movie.get('year'):
                decade = (movie['year'] // 10) * 10
                decades.append(decade)
        
        decade_preferences = Counter(decades)
        
        # Calculate viewing frequency (movies per month)
        watch_dates = [m.get('watch_date') for m in user_movies if m.get('watch_date')]
        viewing_frequency = len(watch_dates) / 12 if watch_dates else 1  # Assume 1 year period
        
        return {
            'genre_preferences': genre_preferences,
            'avg_rating': avg_rating,
            'rating_std': rating_std,
            'decade_preferences': decade_preferences,
            'viewing_frequency': viewing_frequency,
            'highly_rated_count': len(highly_rated)
        }
    
    def _get_candidate_movies(self, user_movies: List[Dict]) -> List[Dict]:
        """Get candidate movies for recommendations (exclude user's history)"""
        # Get popular movies from TMDb
        candidates = self.tmdb_client.get_popular_movies(limit=1000)
        
        # Exclude movies user has already seen
        user_tmdb_ids = {m['tmdb_id'] for m in user_movies}
        candidates = [c for c in candidates if c['tmdb_id'] not in user_tmdb_ids]
        
        return candidates
    
    def _score_candidates(self, candidates: List[Dict], user_profile: Dict) -> List[Dict]:
        """
        Score candidate movies using weighted content-based filtering
        Weights: Genre 40%, Rating Similarity 30%, Popularity 20%, Recency 10%
        """
        scored_candidates = []
        
        genre_preferences = user_profile['genre_preferences']
        avg_rating = user_profile['avg_rating']
        decade_preferences = user_profile['decade_preferences']
        
        for candidate in candidates:
            # Genre score (40% weight)
            genre_score = self._calculate_genre_score(
                candidate.get('genre_ids', []),
                genre_preferences
            )
            
            # Rating similarity score (30% weight)
            rating_score = self._calculate_rating_score(
                candidate.get('rating', 0),
                avg_rating
            )
            
            # Popularity score (20% weight)
            popularity_score = self._calculate_popularity_score(
                candidate.get('popularity', 0)
            )
            
            # Recency score (10% weight)
            recency_score = self._calculate_recency_score(
                candidate.get('year'),
                decade_preferences
            )
            
            # Calculate weighted total score (0-100)
            total_score = (
                genre_score * 0.40 +
                rating_score * 0.30 +
                popularity_score * 0.20 +
                recency_score * 0.10
            )
            
            # Generate reasoning
            reasoning = self._generate_reasoning(
                candidate,
                genre_score,
                rating_score,
                popularity_score,
                genre_preferences
            )
            
            scored_candidates.append({
                'tmdb_id': candidate['tmdb_id'],
                'title': candidate['title'],
                'score': round(total_score, 1),
                'reasoning': reasoning
            })
        
        return scored_candidates
    
    def _calculate_genre_score(self, genre_ids: List[int], genre_preferences: Dict) -> float:
        """Calculate genre match score (0-100)"""
        if not genre_ids or not genre_preferences:
            return 50.0  # Neutral score
        
        # Convert genre IDs to names
        genres = [self.genre_map.get(gid, '') for gid in genre_ids if gid in self.genre_map]
        
        if not genres:
            return 50.0
        
        # Calculate match score
        match_scores = []
        for genre in genres:
            if genre in genre_preferences:
                # Apply 1.5x weight factor for preferred genres
                match_scores.append(genre_preferences[genre] * 1.5)
            else:
                match_scores.append(0.1)  # Small score for non-preferred genres
        
        # Average and normalize to 0-100
        avg_match = np.mean(match_scores)
        score = min(avg_match * 100, 100)
        
        return score
    
    def _calculate_rating_score(self, movie_rating: float, user_avg_rating: float) -> float:
        """Calculate rating similarity score (0-100)"""
        if not movie_rating:
            return 50.0  # Neutral score
        
        # Calculate difference from user's average rating
        diff = abs(movie_rating - user_avg_rating)
        
        # Convert to 0-100 score (smaller diff = higher score)
        score = max(0, 100 - (diff * 10))
        
        return score
    
    def _calculate_popularity_score(self, popularity: float) -> float:
        """Calculate popularity score (0-100)"""
        if not popularity:
            return 50.0
        
        # Normalize popularity (typical range 0-500)
        score = min((popularity / 500) * 100, 100)
        
        return score
    
    def _calculate_recency_score(self, year: int, decade_preferences: Counter) -> float:
        """Calculate recency/decade preference score (0-100)"""
        if not year:
            return 50.0
        
        current_year = datetime.now().year
        decade = (year // 10) * 10
        
        # Boost score if decade matches user preferences
        if decade in decade_preferences:
            return 80.0
        
        # Slight boost for recent movies
        years_old = current_year - year
        if years_old < 5:
            return 70.0
        elif years_old < 10:
            return 60.0
        else:
            return 50.0
    
    def _generate_reasoning(
        self,
        candidate: Dict,
        genre_score: float,
        rating_score: float,
        popularity_score: float,
        genre_preferences: Dict
    ) -> str:
        """Generate human-readable reasoning for recommendation"""
        reasons = []
        
        # Genre match
        genre_ids = candidate.get('genre_ids', [])
        genres = [self.genre_map.get(gid, '') for gid in genre_ids if gid in self.genre_map]
        matching_genres = [g for g in genres if g in genre_preferences]
        
        if matching_genres and genre_score > 70:
            reasons.append(f"Matches your love for {', '.join(matching_genres[:2])}")
        
        # Rating
        movie_rating = candidate.get('rating', 0)
        if movie_rating >= 8.0:
            reasons.append("Highly rated by critics")
        elif movie_rating >= 7.0:
            reasons.append("Well-reviewed")
        
        # Popularity
        if popularity_score > 70:
            reasons.append("Popular choice")
        
        # Year
        year = candidate.get('year')
        if year:
            current_year = datetime.now().year
            if current_year - year < 3:
                reasons.append("Recent release")
        
        return " • ".join(reasons) if reasons else "Recommended based on your preferences"
