# tmdb_service.py - Fetches real movie data (posters, info) from TMDb API

import requests

import streamlit as st
TMDB_API_KEY = st.secrets["TMDB_API_KEY"]
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

def search_movie(query):
    """Searches TMDb for a movie by name. Returns a list of matching results."""
    url = f"{BASE_URL}/search/movie"
    params = {"api_key": TMDB_API_KEY, "query": query}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json().get("results", [])
    return []

def get_movie_details(tmdb_id):
    """Gets full details for a specific movie, including genres."""
    url = f"{BASE_URL}/movie/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    return None

def get_poster_url(poster_path):
    """Builds the full poster image URL from TMDb's relative path."""
    if poster_path:
        return f"{IMAGE_BASE}{poster_path}"
    return None

def get_poster_by_tmdb_id(tmdb_id):
    """Used for our original MovieLens movies - fetches just the poster using links.csv's tmdbId."""
    details = get_movie_details(tmdb_id)
    if details:
        return get_poster_url(details.get("poster_path"))
    return None

from datetime import datetime, timedelta


from datetime import datetime, timedelta

def get_recently_released_movies(days_back=7):
    today = datetime.now().strftime("%Y-%m-%d")
    past_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    url = f"{BASE_URL}/discover/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "sort_by": "popularity.desc",
        "primary_release_date.gte": past_date,
        "primary_release_date.lte": today,
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json().get("results", [])
    return []