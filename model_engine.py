import pandas as pd
import numpy as np
import pickle
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from surprise import Dataset, Reader, SVD
from surprise.model_selection import train_test_split
from surprise import accuracy
import database as db

MOVIES_FILE = 'movies_final.csv'
RATINGS_FILE = 'ratings_final.csv'
MODEL_FILE = 'svd_model.pkl'
CONTENT_SIM_FILE = 'content_sim.pkl'


def load_base_data():
    movies = pd.read_csv(MOVIES_FILE)
    new_movies = db.get_all_new_movies()
    if not new_movies.empty:
        new_movies_formatted = pd.DataFrame({
            'movieId': new_movies['movie_id'] + 200000,
            'clean_title': new_movies['title'],
            'genres': new_movies['genres'],
            'year': new_movies['year'],
            'genres_text': new_movies['genres'].str.replace('|', ' ', regex=False),
        })
        movies = pd.concat([movies, new_movies_formatted], ignore_index=True)
    return movies


def load_combined_ratings():
    ratings = pd.read_csv(RATINGS_FILE)[['userId', 'movieId', 'rating']]
    new_ratings = db.get_all_new_ratings()
    if not new_ratings.empty:
        new_ratings_formatted = new_ratings.rename(columns={'user_id': 'userId', 'movie_id': 'movieId'})
        new_ratings_formatted['userId'] = new_ratings_formatted['userId'] + 1000000
        ratings = pd.concat([ratings, new_ratings_formatted[['userId', 'movieId', 'rating']]], ignore_index=True)
    return ratings


def retrain_model():
    ratings = load_combined_ratings()
    reader = Reader(rating_scale=(0.5, 5.0))
    dataset = Dataset.load_from_df(ratings[['userId', 'movieId', 'rating']], reader)
    trainset, testset = train_test_split(dataset, test_size=0.2, random_state=42)
    algo = SVD()
    algo.fit(trainset)
    predictions = algo.test(testset)
    rmse = accuracy.rmse(predictions, verbose=False)
    mae = accuracy.mae(predictions, verbose=False)
    with open(MODEL_FILE, 'wb') as f:
        pickle.dump(algo, f)
    return algo, rmse, mae, ratings.shape[0]


def retrain_content_model():
    movies = load_base_data()
    movies['genres_text'] = movies['genres_text'].fillna('')
    tfidf = TfidfVectorizer(stop_words='english')
    matrix = tfidf.fit_transform(movies['genres_text'])
    content_sim = cosine_similarity(matrix, matrix)
    with open(CONTENT_SIM_FILE, 'wb') as f:
        pickle.dump(content_sim, f)
    return content_sim, movies


def load_model():
    with open(MODEL_FILE, 'rb') as f:
        return pickle.load(f)


def load_content_sim():
    with open(CONTENT_SIM_FILE, 'rb') as f:
        return pickle.load(f)


def check_movie_exists(tmdb_id, links_df):
    return tmdb_id in links_df['tmdbId'].dropna().astype(int).values


# ---------- Recommendation functions (all 4 types) ----------

def popularity_recommender(movies, ratings, n=10):
    """TYPE 1: Popularity-Based Recommendation"""
    stats = ratings.groupby('movieId').agg(avg_rating=('rating', 'mean'), rating_count=('rating', 'count')).reset_index()
    C = stats['avg_rating'].mean()
    m = 20
    stats['weighted_score'] = (stats['rating_count'] / (stats['rating_count'] + m) * stats['avg_rating']) + (m / (stats['rating_count'] + m) * C)
    result = stats.merge(movies, on='movieId').sort_values('weighted_score', ascending=False)
    return result.head(n)


def content_based_recommender(movie_id, movies, content_sim, n=10):
    """TYPE 2: Content-Based Recommendation"""
    movies = movies.reset_index(drop=True)
    indices = pd.Series(movies.index, index=movies['movieId'])
    if movie_id not in indices:
        return pd.DataFrame()
    idx = indices[movie_id]
    if idx >= content_sim.shape[0]:
        return pd.DataFrame()
    sim_scores = sorted(list(enumerate(content_sim[idx])), key=lambda x: x[1], reverse=True)[1:n+1]
    return movies.iloc[[i[0] for i in sim_scores]]



def collaborative_recommender(user_id, movies, ratings, algo, n=10, excluded_movie_ids=None):
    all_movies = movies['movieId'].unique()
    rated = ratings[ratings['userId'] == user_id]['movieId'].tolist()
    excluded = set(rated) | set(excluded_movie_ids or [])
    to_predict = [m for m in all_movies if m not in excluded]
    predictions = sorted([(m, algo.predict(user_id, m).est) for m in to_predict], key=lambda x: x[1], reverse=True)[:n]
    result = pd.DataFrame(predictions, columns=['movieId', 'PredictedRating'])
    result['PredictedRating'] = result['PredictedRating'].round(2)
    return result.merge(movies, on='movieId')


def hybrid_recommender(user_id, movie_id, movies, content_sim, algo, n=10):
    """TYPE 4: Hybrid Recommendation (Content similarity + Collaborative personalization)"""
    content_recs = content_based_recommender(movie_id, movies, content_sim, n=20)
    if content_recs.empty:
        return pd.DataFrame()
    scored = []
    for _, row in content_recs.iterrows():
        pred = algo.predict(user_id, row['movieId']).est
        scored.append((row['movieId'], row['clean_title'], round(pred, 2)))
    scored.sort(key=lambda x: x[2], reverse=True)
    return pd.DataFrame(scored[:n], columns=['movieId', 'clean_title', 'HybridScore'])


def is_cold_start_user(user_id, ratings, min_ratings=5):
    count = ratings[ratings['userId'] == user_id].shape[0]
    return count < min_ratings


def also_watched_recommender(movie_id, ratings, movies, n=8):
    """'Customers Also Bought' - finds movies liked by users who also liked this one."""
    fans = ratings[(ratings['movieId'] == movie_id) & (ratings['rating'] >= 4)]['userId'].unique()
    if len(fans) == 0:
        return pd.DataFrame()
    other_ratings = ratings[
        (ratings['userId'].isin(fans)) & (ratings['movieId'] != movie_id) & (ratings['rating'] >= 4)
    ]
    counts = other_ratings.groupby('movieId').size().reset_index(name='co_rating_count')
    counts = counts.sort_values('co_rating_count', ascending=False).head(n)
    return counts.merge(movies, on='movieId')