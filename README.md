# MovieMind — AI-Powered Movie Recommendation System

A full-stack movie recommendation platform built with the MovieLens dataset,
featuring popularity-based, content-based, collaborative filtering, and hybrid
recommendation approaches, deployed as a Streamlit web application.

## Features
- User authentication (Sign Up/Login, Admin/User roles)
- 4 recommendation types: Popularity, Content-Based, Collaborative Filtering, Hybrid
- TMDb API integration for posters and story summaries
- AI Chatbot Assistant (Groq API)
- Admin Panel for catalog management and model retraining
- Automatic new-release syncing

## Tech Stack
Python, Streamlit, scikit-learn, Surprise (SVD), SQLite, TMDb API, Groq API

## Setup
1. `pip install -r requirements.txt`
2. Add your API keys to `.streamlit/secrets.toml`:
GROQ_API_KEY = "your-key"
TMDB_API_KEY = "your-key"
3. `streamlit run app.py`