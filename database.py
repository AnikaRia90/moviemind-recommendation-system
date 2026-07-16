import sqlite3
import hashlib
import pandas as pd

DB_NAME = "movies.db"

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS new_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            movie_id INTEGER NOT NULL,
            rating REAL NOT NULL,
            rated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS new_movies (
            movie_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tmdb_id INTEGER UNIQUE,
            title TEXT NOT NULL,
            genres TEXT,
            year INTEGER,
            poster_url TEXT,
            overview TEXT,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            movie_id INTEGER NOT NULL,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            synced_at TEXT DEFAULT CURRENT_TIMESTAMP,
            movies_added INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            movie_id INTEGER NOT NULL,
            is_helpful INTEGER NOT NULL,
            given_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(name, email, password, is_admin=0):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (name, email, password_hash, is_admin) VALUES (?, ?, ?, ?)",
            (name, email, hash_password(password), is_admin)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def verify_user(identifier, password):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, password_hash, is_admin FROM users WHERE email = ? OR name = ?",
        (identifier, identifier)
    )
    row = cursor.fetchone()
    conn.close()
    if row and row[2] == hash_password(password):
        return {"id": row[0], "name": row[1], "is_admin": bool(row[3])}
    return None

def get_user_by_id(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, is_admin FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "name": row[1], "is_admin": bool(row[2])}
    return None

def add_rating(user_id, movie_id, rating):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO new_ratings (user_id, movie_id, rating) VALUES (?, ?, ?)",
        (user_id, movie_id, rating)
    )
    conn.commit()
    conn.close()

def get_all_new_ratings():
    conn = get_connection()
    df = pd.read_sql_query("SELECT user_id, movie_id, rating FROM new_ratings", conn)
    conn.close()
    return df

def get_user_ratings(user_id):
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT movie_id, rating, rated_at FROM new_ratings WHERE user_id = ?", conn, params=(user_id,)
    )
    conn.close()
    return df

def get_user_rating_for_movie(user_id, movie_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT rating, rated_at FROM new_ratings WHERE user_id = ? AND movie_id = ? ORDER BY rated_at DESC LIMIT 1",
        (user_id, movie_id)
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"rating": row[0], "rated_at": row[1]}
    return None

def add_new_movie(tmdb_id, title, genres, year, poster_url, overview):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO new_movies (tmdb_id, title, genres, year, poster_url, overview) VALUES (?, ?, ?, ?, ?, ?)",
            (tmdb_id, title, genres, year, poster_url, overview)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_all_new_movies():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM new_movies", conn)
    conn.close()
    return df

def add_to_watchlist(user_id, movie_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO watchlist (user_id, movie_id) VALUES (?, ?)", (user_id, movie_id))
    conn.commit()
    conn.close()

def get_watchlist(user_id):
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT movie_id, added_at FROM watchlist WHERE user_id = ?", conn, params=(user_id,)
    )
    conn.close()
    return df

def is_in_watchlist(user_id, movie_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM watchlist WHERE user_id = ? AND movie_id = ?", (user_id, movie_id))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def log_sync(movies_added):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO sync_log (movies_added) VALUES (?)", (movies_added,))
    conn.commit()
    conn.close()

def get_last_sync():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT synced_at, movies_added FROM sync_log ORDER BY synced_at DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"synced_at": row[0], "movies_added": row[1]}
    return None

def add_feedback(user_id, movie_id, is_helpful):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO feedback (user_id, movie_id, is_helpful) VALUES (?, ?, ?)",
        (user_id, movie_id, 1 if is_helpful else 0)
    )
    conn.commit()
    conn.close()

def get_disliked_movie_ids(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT movie_id FROM feedback WHERE user_id = ? AND is_helpful = 0", (user_id,))
    ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    return ids