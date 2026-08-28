import os
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

class DestinationRecommender:
    def __init__(self, csv_path=None):
        if csv_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            csv_path = os.path.join(base_dir, 'datasets', 'destinations.csv')
        
        self.csv_path = csv_path
        self.df = None
        self.vectorizer = None
        self.tfidf_matrix = None
        self._load_and_prepare()

    def _load_and_prepare(self):
        """Loads destination CSV and fits TF-IDF Vectorizer on combined text features."""
        if not os.path.exists(self.csv_path):
            raise FileNotFoundError(f"Destinations dataset not found at {self.csv_path}")
        
        self.df = pd.read_csv(self.csv_path)
        self.df.fillna('', inplace=True)
        
        # Combine text features for vectorization
        self.df['combined_features'] = (
            self.df['category'] + " " +
            self.df['state'] + " " +
            self.df['tags'] + " " +
            self.df['description']
        ).str.lower()
        
        self.vectorizer = TfidfVectorizer(stop_words='english')
        self.tfidf_matrix = self.vectorizer.fit_transform(self.df['combined_features'])

    def recommend(self, budget_level=None, category=None, interests=None, preferred_state=None, top_n=5):
        """
        Recommends top N destinations based on user criteria using TF-IDF and Cosine Similarity.
        
        Parameters:
        - budget_level: 'Budget', 'Moderate', 'Luxury', or None/Any
        - category: e.g. 'Beach', 'Mountain', 'Heritage', etc.
        - interests: list of interest strings or a single comma/space-separated string
        - preferred_state: state/country preference string
        - top_n: number of recommendations to return
        
        Returns:
        - list of dicts with destination details and similarity score
        """
        if self.df is None or self.vectorizer is None:
            self._load_and_prepare()

        # Build user search query string
        query_parts = []
        if category and category.strip().lower() != 'any':
            query_parts.append(category.strip())
        if preferred_state and preferred_state.strip().lower() != 'any':
            query_parts.append(preferred_state.strip())
        
        if interests:
            if isinstance(interests, list):
                query_parts.extend([str(i).strip() for i in interests if i])
            elif isinstance(interests, str):
                query_parts.append(interests.strip())
                
        user_query = " ".join(query_parts).lower()
        
        # If user query is completely empty, use category or default to general travel keywords
        if not user_query.strip():
            user_query = "nature culture beach mountain heritage adventure"

        # Transform user query into TF-IDF vector
        query_vector = self.vectorizer.transform([user_query])
        
        # Calculate Cosine Similarity against all destinations
        cosine_sim = cosine_similarity(query_vector, self.tfidf_matrix).flatten()

        # Filter dataset by budget_level if specified
        filtered_indices = list(range(len(self.df)))
        if budget_level and budget_level.strip().lower() != 'any':
            budget_str = budget_level.strip().lower()
            filtered_indices = [
                idx for idx, row in self.df.iterrows()
                if row['budget_level'].lower() == budget_str
            ]
            # If no matches after budget filtering, fall back to all indices
            if not filtered_indices:
                filtered_indices = list(range(len(self.df)))

        # Rank filtered destinations by cosine similarity score
        scored_candidates = []
        for idx in filtered_indices:
            score = float(cosine_sim[idx])
            # Boost score slightly if category or state matches exactly
            row = self.df.iloc[idx]
            if category and category.lower() in row['category'].lower():
                score += 0.15
            if preferred_state and preferred_state.lower() in row['state'].lower():
                score += 0.20
            
            scored_candidates.append((idx, score))

        # Sort candidate destinations by score descending
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        top_indices = scored_candidates[:top_n]

        results = []
        for idx, score in top_indices:
            row = self.df.iloc[idx].to_dict()
            row['score'] = round(score, 4)
            # Remove combined_features from output
            row.pop('combined_features', None)
            results.append(row)

        return results

# Convenience instance for easy importing
recommender_engine = DestinationRecommender()

def get_recommendations(budget_level=None, category=None, interests=None, preferred_state=None, top_n=5):
    """Standalone wrapper function to call recommender engine."""
    return recommender_engine.recommend(
        budget_level=budget_level,
        category=category,
        interests=interests,
        preferred_state=preferred_state,
        top_n=top_n
    )
