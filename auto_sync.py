# auto_sync.py - Runs in the background, periodically checking TMDb for new releases
# and automatically adding any that aren't already in our catalog.

import time
import threading
import database as db
import model_engine as engine
import tmdb_service as tmdb

SYNC_INTERVAL_SECONDS = 3600  # check once every hour

def sync_new_releases():
    """One sync cycle: fetch recent releases, add any that are missing."""
    links_df = tmdb.pd.read_csv('links.csv') if False else None  # placeholder, replaced below
    import pandas as pd
    links_df = pd.read_csv('links.csv')

    recent = tmdb.get_recently_released_movies(days_back=7)
    added_count = 0

    existing_new = db.get_all_new_movies()
    existing_tmdb_ids = set(existing_new['tmdb_id'].values) if not existing_new.empty else set()
    original_tmdb_ids = set(links_df['tmdbId'].dropna().astype(int).values)

    for r in recent:
        tmdb_id = r['id']
        if tmdb_id in original_tmdb_ids or tmdb_id in existing_tmdb_ids:
            continue  # already have this movie

        details = tmdb.get_movie_details(tmdb_id)
        if not details:
            continue
        genres = '|'.join([g['name'] for g in details.get('genres', [])]) or 'Unknown'
        year = int(r.get('release_date', '0000')[:4]) if r.get('release_date') else None

        added = db.add_new_movie(
            tmdb_id=tmdb_id, title=r['title'], genres=genres, year=year,
            poster_url=tmdb.get_poster_url(r.get('poster_path')), overview=r.get('overview', '')
        )
        if added:
            added_count += 1

    db.log_sync(added_count)
    return added_count

def background_loop():
    """Runs forever in a background thread, syncing every SYNC_INTERVAL_SECONDS."""
    while True:
        try:
            sync_new_releases()
        except Exception as e:
            print(f"Auto-sync error: {e}")
        time.sleep(SYNC_INTERVAL_SECONDS)

_sync_thread_started = False

def start_background_sync():
    """Starts the background thread once (safe to call multiple times)."""
    global _sync_thread_started
    if not _sync_thread_started:
        thread = threading.Thread(target=background_loop, daemon=True)
        thread.start()
        _sync_thread_started = True