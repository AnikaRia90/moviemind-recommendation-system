import streamlit as st
import pandas as pd
import numpy as np
import re
import auto_sync
import database as db
import model_engine as engine
import tmdb_service as tmdb
import chatbot_service as chatbot
from streamlit_option_menu import option_menu

db.init_db()
auto_sync.start_background_sync()
st.set_page_config(page_title="MovieMind", page_icon="🎬", layout="wide")

def load_css(path):
    with open(path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
load_css("style.css")

@st.cache_data
def get_movies():
    return engine.load_base_data()

@st.cache_data
def get_ratings():
    return engine.load_combined_ratings()

@st.cache_resource
def get_model():
    return engine.load_model()

@st.cache_resource
def get_content_sim():
    return engine.load_content_sim()

@st.cache_data
def get_links():
    return pd.read_csv('links.csv')

movies = get_movies()
ratings = get_ratings()
algo = get_model()
content_sim = get_content_sim()
links = get_links()

@st.cache_data(show_spinner=False)
def get_poster(movie_id):
    if movie_id >= 200000:
        new_movies = db.get_all_new_movies()
        match = new_movies[new_movies['movie_id'] + 200000 == movie_id]
        if not match.empty and pd.notna(match['poster_url'].values[0]):
            return match['poster_url'].values[0]
        return "https://via.placeholder.com/300x450/1a1a2e/ffffff?text=No+Poster"
    match = links[links['movieId'] == movie_id]
    if not match.empty and pd.notna(match['tmdbId'].values[0]):
        url = tmdb.get_poster_by_tmdb_id(int(match['tmdbId'].values[0]))
        if url:
            return url
    return "https://via.placeholder.com/300x450/1a1a2e/ffffff?text=No+Poster"

@st.cache_data(show_spinner=False)
def get_movie_overview(movie_id):
    if movie_id >= 200000:
        new_movies = db.get_all_new_movies()
        match = new_movies[new_movies['movie_id'] + 200000 == movie_id]
        if not match.empty:
            return match['overview'].values[0] or "No story summary available."
        return "No story summary available."
    match = links[links['movieId'] == movie_id]
    if not match.empty and pd.notna(match['tmdbId'].values[0]):
        details = tmdb.get_movie_details(int(match['tmdbId'].values[0]))
        if details:
            return details.get('overview') or "No story summary available."
    return "No story summary available."

# ---------- Session state ----------
for key, default in [('logged_in', False), ('user_id', None), ('user_name', None), ('is_admin', False)]:
    if key not in st.session_state:
        st.session_state[key] = default
if "prev_nav" not in st.session_state:
    st.session_state.prev_nav = "Home"
if "selected_movie" not in st.session_state:
    st.session_state.selected_movie = None
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

if not st.session_state.logged_in and "uid" in st.query_params:
    try:
        restored = db.get_user_by_id(int(st.query_params["uid"]))
        if restored:
            st.session_state.update(logged_in=True, user_id=restored['id'],
                                     user_name=restored['name'], is_admin=restored['is_admin'])
    except Exception:
        pass

# ---------- UI Components ----------
def render_movie_card(movie_id, title, meta_line="", score=None, explanation=""):
    poster = get_poster(movie_id)
    score_html = f'<span class="score-badge">{score}</span>' if score is not None else ""
    display_title = title if len(str(title)) < 35 else str(title)[:32] + "..."

    movie_ratings = ratings[ratings['movieId'] == movie_id]
    if not movie_ratings.empty:
        avg = movie_ratings['rating'].mean()
        rating_html = f'<span style="color:#ffd700;">⭐ {avg:.1f}</span> <span style="color:#888;">({movie_ratings.shape[0]})</span>'
    else:
        rating_html = '<span style="color:#888;">No ratings yet</span>'

    extra_html = f'<div class="movie-meta">{meta_line} {score_html}</div>' if (meta_line or score is not None) else ""
    explanation_html = f'<div class="movie-meta" style="color:#f4a261; font-style:italic;">💡 {explanation}</div>' if explanation else ""

    your_rating_html = ""
    if st.session_state.logged_in:
        your_rating = db.get_user_rating_for_movie(st.session_state.user_id, movie_id)
        if your_rating:
            rating_value = your_rating["rating"]
            your_rating_html = (
                '<div class="movie-meta" style="color:#4cc9f0;">'
                f'✅ You rated this: ⭐ {rating_value:.0f}/5</div>'
            )
    card_html = (
        '<div class="movie-card">'
        f'<img src="{poster}" class="movie-poster">'
        f'<div class="movie-title">{display_title}</div>'
        f'<div class="movie-meta">{rating_html}</div>'
        f'{extra_html}'
        f'{your_rating_html}'
        f'{explanation_html}'
        '</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)

    if st.session_state.logged_in:
        b1, b2 = st.columns(2)
        with b1:
            if st.button("🎬 Details", key=f"det_{movie_id}_{title[:8]}", use_container_width=True):
                st.session_state.selected_movie = movie_id
                st.rerun()
        with b2:
            if db.is_in_watchlist(st.session_state.user_id, movie_id):
                st.button("✅ Saved", key=f"wl_{movie_id}_{title[:8]}", disabled=True, use_container_width=True)
            else:
                if st.button("➕ Save", key=f"wl_{movie_id}_{title[:8]}", use_container_width=True):
                    db.add_to_watchlist(st.session_state.user_id, movie_id)
                    st.rerun()

        existing_rating = db.get_user_rating_for_movie(st.session_state.user_id, movie_id)
        default_idx = int(existing_rating["rating"]) - 1 if existing_rating else 4
        rate_label = "⭐ Update Rating" if existing_rating else "⭐ Rate this movie"

        with st.popover(rate_label, use_container_width=True):
            rating_val = st.selectbox("Your rating", [1, 2, 3, 4, 5], index=default_idx, key=f"rate_{movie_id}_{title[:8]}")
            if st.button("Submit", key=f"submit_{movie_id}_{title[:8]}", use_container_width=True):
                db.add_rating(st.session_state.user_id, movie_id, float(rating_val))
                st.toast(f"Rated {rating_val} stars!")
                st.rerun()

        if score is not None:
            fb1, fb2 = st.columns(2)
            with fb1:
                if st.button("👍 Helpful", key=f"fbup_{movie_id}_{title[:8]}", use_container_width=True):
                    db.add_feedback(st.session_state.user_id, movie_id, True)
                    st.toast("Thanks for your feedback!")
            with fb2:
                if st.button("👎 Not for me", key=f"fbdown_{movie_id}_{title[:8]}", use_container_width=True):
                    db.add_feedback(st.session_state.user_id, movie_id, False)
                    st.toast("Thanks, we'll improve!")

    else:
        if st.button("🎬 Details", key=f"det_{movie_id}_{title[:8]}", use_container_width=True):
            st.session_state.selected_movie = movie_id
            st.rerun()

def render_movie_grid(df, id_col, title_col, meta_col=None, score_col=None, cols=5, explanation_fn=None):
    if df.empty:
        st.info("No movies found.")
        return
    columns = st.columns(cols)
    for i, (_, row) in enumerate(df.iterrows()):
        with columns[i % cols]:
            meta = f"{meta_col}: {row[meta_col]:.2f}" if meta_col and pd.notna(row.get(meta_col)) else ""
            score = row[score_col] if score_col else None
            explanation = explanation_fn(row) if explanation_fn else ""
            render_movie_card(row[id_col], row[title_col], meta, score, explanation)

COMMON_WORDS = {"the", "a", "an", "of", "and", "or", "is", "in", "on", "for", "with", "to",
                "man", "men", "woman", "world", "story", "movie", "film", "part"}

def normalize_text(text):
    return re.sub(r'[^a-z0-9 ]', ' ', str(text).lower())

def search_catalog_for_ai(query, movies, n=8):
    query_norm = normalize_text(query)
    movies_norm = movies['clean_title'].apply(normalize_text)

    # 1. Try exact phrase match first
    phrase_matches = movies[movies_norm.str.contains(query_norm, na=False, regex=False)]
    if not phrase_matches.empty:
        return phrase_matches.head(n)

    # 2. Try direct case-insensitive match on the RAW title (backup, catches edge cases)
    raw_matches = movies[movies['clean_title'].str.lower().str.contains(query.lower().strip(), na=False, regex=False)]
    if not raw_matches.empty:
        return raw_matches.head(n)

    # 3. Fallback: match on individual meaningful words
    words = [w for w in query_norm.split() if len(w) > 2 and w not in COMMON_WORDS]
    if not words:
        return pd.DataFrame()
    pattern = '|'.join(words)
    matches = movies[movies_norm.str.contains(pattern, na=False, regex=True)]
    return matches.head(n)

def get_user_personal_context(user_id, matched_movies):
    """Reports a movie as 'already seen' if the user either rated it OR saved it to their
    watchlist. Rated movies include the star rating; watchlist-only movies just say seen."""
    if not user_id or matched_movies.empty:
        return ""

    user_ratings_df = db.get_user_ratings(user_id)
    user_watchlist_df = db.get_watchlist(user_id)

    lines = []
    for _, m in matched_movies.iterrows():
        rating_match = user_ratings_df[user_ratings_df['movie_id'] == m['movieId']] if not user_ratings_df.empty else pd.DataFrame()
        watchlist_match = user_watchlist_df[user_watchlist_df['movie_id'] == m['movieId']] if not user_watchlist_df.empty else pd.DataFrame()

        if not rating_match.empty:
            r = rating_match.iloc[0]
            lines.append(
                f'- The user has already seen "{m["clean_title"]}" and rated it '
                f'{r["rating"]:.0f}/5 stars on {r["rated_at"]}.'
            )
        elif not watchlist_match.empty:
            w = watchlist_match.iloc[0]
            lines.append(
                f'- The user has already seen "{m["clean_title"]}" '
                f'(saved to their watchlist on {w["added_at"]}, no star rating given).'
            )

    if not lines:
        return ""
    return "User's personal watch history for these movies:\n" + "\n".join(lines)

# ---------- Top bar ----------
tcol1, tcol2, tcol3 = st.columns([2, 3, 2])

with tcol1:
    st.markdown("### 🎬 MovieMind")

with tcol2:
    search_query = st.selectbox(
        "", options=[""] + sorted(movies['clean_title'].dropna().unique().tolist()),
        placeholder="🔍 Search movies...", label_visibility="collapsed",
        key=f"search_{st.session_state.prev_nav}"
    )

with tcol3:
    if st.session_state.logged_in:
        with st.popover(f"👤 {st.session_state.user_name}", use_container_width=True):
            st.write(f"**{st.session_state.user_name}**" + (" (Admin)" if st.session_state.is_admin else ""))
            if st.button("Logout", use_container_width=True):
                for k in ['logged_in', 'user_id', 'user_name', 'is_admin']:
                    st.session_state[k] = False if k == 'logged_in' else None
                st.query_params.clear()
                st.rerun()
    else:
        with st.popover("👤 Account", use_container_width=True):
            t1, t2, t3 = st.tabs(["Sign Up", "Admin Sign Up", "Login"])

            with t1:
                with st.form("signup"):
                    name = st.text_input("Full Name")
                    email = st.text_input("Email")
                    pw = st.text_input("Password", type="password")
                    if st.form_submit_button("Create Account"):
                        if name.strip() and email.strip() and pw.strip():
                            uid = db.create_user(name, email, pw, is_admin=0)
                            if uid:
                                st.session_state.update(logged_in=True, user_id=uid, user_name=name, is_admin=False)
                                st.query_params["uid"] = str(uid)
                                st.rerun()
                            else:
                                st.error("Email already registered.")
                        else:
                            st.error("Please fill all fields.")

            with t2:
                st.caption("For platform administrators only.")
                with st.form("admin_signup"):
                    a_name = st.text_input("Full Name", key="a_name")
                    a_email = st.text_input("Email", key="a_email")
                    a_pw = st.text_input("Password", type="password", key="a_pw")
                    a_code = st.text_input("Admin Access Code", type="password")
                    if st.form_submit_button("Create Admin Account"):
                        if a_code != "admin123":
                            st.error("Invalid admin access code.")
                        elif a_name.strip() and a_email.strip() and a_pw.strip():
                            uid = db.create_user(a_name, a_email, a_pw, is_admin=1)
                            if uid:
                                st.session_state.update(logged_in=True, user_id=uid, user_name=a_name, is_admin=True)
                                st.query_params["uid"] = str(uid)
                                st.rerun()
                            else:
                                st.error("Email already registered.")
                        else:
                            st.error("Please fill all fields.")

            with t3:
                with st.form("login"):
                    identifier = st.text_input("Email or Username")
                    pw = st.text_input("Password", type="password")
                    if st.form_submit_button("Login"):
                        user = db.verify_user(identifier, pw)
                        if user:
                            st.session_state.update(logged_in=True, user_id=user['id'], user_name=user['name'], is_admin=user['is_admin'])
                            st.query_params["uid"] = str(user['id'])
                            st.rerun()
                        else:
                            st.error("Invalid credentials.")

st.markdown("<hr style='margin-top:0; border-color:#333;'>", unsafe_allow_html=True)

# =========================================================
# MOVIE DETAIL VIEW
# =========================================================
if st.session_state.selected_movie is not None:
    mid = st.session_state.selected_movie
    movie_row = movies[movies['movieId'] == mid]

    if st.button("⬅ Back"):
        st.session_state.selected_movie = None
        st.rerun()

    if not movie_row.empty:
        row = movie_row.iloc[0]
        c1, c2 = st.columns([1, 2])
        with c1:
            st.image(get_poster(mid), use_container_width=True)
        with c2:
            st.title(row['clean_title'])
            st.caption(f"📅 {int(row['year']) if pd.notna(row['year']) else 'Unknown'}  |  🎭 {row['genres']}")

            movie_ratings = ratings[ratings['movieId'] == mid]
            if not movie_ratings.empty:
                st.metric("Average Rating", f"⭐ {movie_ratings['rating'].mean():.2f} / 5", f"{movie_ratings.shape[0]} ratings")
            else:
                st.info("No ratings yet for this movie.")

            if st.session_state.logged_in:
                your_rating = db.get_user_rating_for_movie(st.session_state.user_id, mid)
                if your_rating:
                    st.success(f"✅ You rated this movie: ⭐ {your_rating['rating']:.0f}/5")
                elif db.is_in_watchlist(st.session_state.user_id, mid):
                    st.info("📌 This movie is in your watchlist.")

            st.subheader("Story")
            st.write(get_movie_overview(mid))

            if st.session_state.logged_in:
                st.divider()
                cc1, cc2 = st.columns(2)
                with cc1:
                    if db.is_in_watchlist(st.session_state.user_id, mid):
                        st.button("✅ Saved to Watchlist", disabled=True)
                    else:
                        if st.button("➕ Add to Watchlist"):
                            db.add_to_watchlist(st.session_state.user_id, mid)
                            st.rerun()
                with cc2:
                    existing_rating = db.get_user_rating_for_movie(st.session_state.user_id, mid)
                    options = [None, 1, 2, 3, 4, 5]
                    default_idx = options.index(int(existing_rating["rating"])) if existing_rating else 0
                    label = "Update your rating" if existing_rating else "Rate this movie"

                    rating_val = st.selectbox(label, options, index=default_idx)
                    if rating_val:
                        db.add_rating(st.session_state.user_id, mid, float(rating_val))
                        st.toast(f"Rated {rating_val} stars!")
                        st.rerun()

    st.divider()
    st.subheader("You might also like")
    similar = engine.content_based_recommender(mid, movies, content_sim, n=5)
    render_movie_grid(similar, 'movieId', 'clean_title', cols=5)

    also_watched = engine.also_watched_recommender(mid, ratings, movies, n=5)
    if not also_watched.empty:
        st.divider()
        st.subheader("🛒 Customers Also Watched")
        st.caption("People who liked this movie also enjoyed these.")
        render_movie_grid(also_watched, 'movieId', 'clean_title', meta_col='co_rating_count', cols=5)

# =========================================================
# NORMAL NAVIGATION + PAGES
# =========================================================
else:
    menu_options = ["Home", "Browse", "Similar Movies", "Recommended", "Watchlist", "AI Assistant"]
    menu_icons = ["house", "grid", "link-45deg", "bullseye", "bookmark-heart", "robot"]
    if st.session_state.is_admin:
        menu_options.append("Admin Panel")
        menu_icons.append("gear")

    selected = option_menu(
        menu_title=None, options=menu_options, icons=menu_icons, orientation="horizontal", default_index=0,
        key="main_nav_menu",
        styles={"container": {"background-color": "#1a1a2e"}, "nav-link": {"color": "white", "font-size": "13px"},
                "nav-link-selected": {"background-color": "#e50914"}}
    )

    if selected != st.session_state.prev_nav:
        st.session_state.prev_nav = selected
        st.rerun()

    if search_query:
        st.header(f"Search results for '{search_query}'")
        matches = movies[movies['clean_title'] == search_query]
        render_movie_grid(matches, 'movieId', 'clean_title', cols=5)

    elif selected == "Home":
        st.markdown('<div class="main-header"><h1>Welcome to MovieMind</h1><p>Movies picked just for you, powered by machine learning.</p></div>', unsafe_allow_html=True)

        if st.session_state.is_admin:
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Movies", f"{movies['movieId'].nunique():,}")
            c2.metric("Total Users", f"{ratings['userId'].nunique():,}")
            c3.metric("Total Ratings", f"{ratings.shape[0]:,}")

        new_movies_df = db.get_all_new_movies()
        if not new_movies_df.empty:
            st.subheader("🆕 New Releases")
            st.caption("Freshly added to our catalog.")
            new_movies_df = new_movies_df.sort_values('added_at', ascending=False).head(5)
            display_df = new_movies_df.copy()
            display_df['movieId'] = display_df['movie_id'] + 200000
            display_df['clean_title'] = display_df['title']
            render_movie_grid(display_df, 'movieId', 'clean_title', cols=5)

        st.subheader("🔥 Top Rated Movies (Popularity-Based)")
        top = engine.popularity_recommender(movies, ratings, n=10)
        render_movie_grid(top, 'movieId', 'clean_title', meta_col='avg_rating', cols=5)

    elif selected == "Browse":
        st.header("Browse All Movies")
        f1, f2, f3 = st.columns(3)
        with f1:
            genre_filter = st.selectbox("Genre", ["All"] + sorted(set('|'.join(movies['genres'].dropna()).split('|'))))
        with f2:
            year_range = st.slider("Year Range", 1900, 2026, (1990, 2026))
        with f3:
            sort_by = st.selectbox("Sort by", ["Most Popular", "Highest Rated", "Newest"])

        filtered = movies.copy()
        if genre_filter != "All":
            filtered = filtered[filtered['genres'].str.contains(genre_filter, na=False)]
        filtered = filtered[(filtered['year'] >= year_range[0]) & (filtered['year'] <= year_range[1])]

        if sort_by == "Highest Rated":
            stats = ratings.groupby('movieId')['rating'].mean().reset_index(name='avg_rating')
            filtered = filtered.merge(stats, on='movieId', how='left').sort_values('avg_rating', ascending=False)
        elif sort_by == "Newest":
            filtered = filtered.sort_values('year', ascending=False)
        else:
            counts = ratings.groupby('movieId').size().reset_index(name='rating_count')
            filtered = filtered.merge(counts, on='movieId', how='left').sort_values('rating_count', ascending=False)

        render_movie_grid(filtered.head(20), 'movieId', 'clean_title', cols=5)

    elif selected == "Similar Movies":
        st.header("Content-Based Recommendations")
        st.caption("Finds movies with similar genres to the one you pick.")
        choice = st.selectbox("Pick a movie", movies['clean_title'].values)
        mid = movies[movies['clean_title'] == choice]['movieId'].values[0]
        if st.button("Find Similar"):
            results = engine.content_based_recommender(mid, movies, content_sim, n=10)
            render_movie_grid(results, 'movieId', 'clean_title', cols=5)

    elif selected == "Recommended":
        st.header("Recommended For You")
        if not st.session_state.logged_in:
            st.warning("Please login first (top-right Account button).")
        else:
            uid = st.session_state.user_id
            if engine.is_cold_start_user(uid, ratings):
                st.info("Rate a few movies to unlock personalized picks. Showing top-rated movies for now.")
                results = engine.popularity_recommender(movies, ratings, n=10)
                render_movie_grid(results, 'movieId', 'clean_title', meta_col='avg_rating', cols=5)
            else:
                tab1, tab2 = st.tabs(["Collaborative Filtering", "Hybrid Recommendation"])
                with tab1:
                    st.caption("Based on ratings from users with similar taste to yours.")
                    excluded = db.get_disliked_movie_ids(uid)
                    results = engine.collaborative_recommender(uid, movies, ratings, algo, n=10, excluded_movie_ids=excluded)
                    render_movie_grid(
                        results, 'movieId', 'clean_title', score_col='PredictedRating', cols=5,
                        explanation_fn=lambda row: f"Predicted {row['PredictedRating']:.1f}/5 based on users like you"
                    )
                with tab2:
                    st.caption("Combines content similarity with your personal taste.")
                    choice = st.selectbox("Pick a movie you like", movies['clean_title'].values, key="hybrid_select")
                    mid = movies[movies['clean_title'] == choice]['movieId'].values[0]
                    if st.button("Get Hybrid Recommendations"):
                        results = engine.hybrid_recommender(uid, mid, movies, content_sim, algo, n=10)
                        render_movie_grid(results, 'movieId', 'clean_title', score_col='HybridScore', cols=5,
                            explanation_fn=lambda row: f"Similar to '{choice}' and matches your taste")
    elif selected == "Watchlist":
        st.header("My Watchlist")
        if not st.session_state.logged_in:
            st.warning("Please login first.")
        else:
            wl = db.get_watchlist(st.session_state.user_id)
            if wl.empty:
                st.info("Your watchlist is empty.")
            else:
                wl_movies = movies[movies['movieId'].isin(wl['movie_id'])]
                render_movie_grid(wl_movies, 'movieId', 'clean_title', cols=5)

    elif selected == "AI Assistant":
        st.header("🤖 Ask MovieMind AI")
        st.caption("Chat about movies, get recommendations, or ask anything film-related.")

        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        user_input = st.chat_input("Ask me about movies...")

        if user_input:
            st.session_state.chat_messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.write(user_input)

            search_matches = search_catalog_for_ai(user_input, movies, n=8)
            top_movies = engine.popularity_recommender(movies, ratings, n=5)

            context_parts = []
            if not search_matches.empty:
                context_parts.append(
                    "Movies found in our catalog matching this query:\n" +
                    "\n".join(
                        f"- {row['clean_title']} ({row['genres']}, year {int(row['year']) if pd.notna(row['year']) else 'N/A'})"
                        for _, row in search_matches.iterrows()
                    )
                )
                top_match = search_matches.iloc[0]
                overview = get_movie_overview(top_match['movieId'])
                context_parts.append(f'Story summary for "{top_match["clean_title"]}": {overview}')

                if st.session_state.logged_in:
                    personal_context = get_user_personal_context(st.session_state.user_id, search_matches)
                    if personal_context:
                        context_parts.append(personal_context)

            context_parts.append(
                "Currently trending/popular movies in our catalog:\n" +
                "\n".join(
                    f"- {row['clean_title']} ({row['genres']}, avg rating {row['avg_rating']:.1f})"
                    for _, row in top_movies.iterrows()
                )
            )
            catalog_context = "\n\n".join(context_parts)

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    reply = chatbot.get_chat_response(
                        user_input, st.session_state.chat_messages[:-1], catalog_context
                    )
                st.write(reply)

            st.session_state.chat_messages.append({"role": "assistant", "content": reply})
            st.rerun()

        if st.session_state.chat_messages:
            if st.button("🗑️ Clear Chat"):
                st.session_state.chat_messages = []
                st.rerun()

    elif selected == "Admin Panel":
        st.header("🛠️ Admin Panel")
        tab0, tab1, tab2 = st.tabs(["Dashboard", "Add New Movie", "Retrain Model"])

        with tab0:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Movies", f"{movies['movieId'].nunique():,}")
            c2.metric("Total Users", f"{ratings['userId'].nunique():,}")
            c3.metric("Total Ratings", f"{ratings.shape[0]:,}")
            c4.metric("Admin-Added Movies", f"{db.get_all_new_movies().shape[0]:,}")

            last_sync = db.get_last_sync()
            if last_sync:
                st.info(f"🔄 Last auto-sync: {last_sync['synced_at']} — {last_sync['movies_added']} new movies")

        last_sync = db.get_last_sync()
        if last_sync:
            st.info(f"🔄 Last auto-sync: {last_sync['synced_at']} — {last_sync['movies_added']} new movies added")
        else:
            st.info("🔄 Auto-sync will run within the next hour (checks every hour automatically)")

        if st.button("⚡ Force Sync Now (for testing)"):
            with st.spinner("Checking TMDb for new releases..."):
                added = auto_sync.sync_new_releases()
            st.success(f"Sync complete! Added {added} new movies.")
            st.cache_data.clear()
            st.rerun()
        st.divider()
        with tab1:
            st.write("Search TMDb and add a new movie to the catalog.")
            search_term = st.text_input("Search movie title")
            if search_term:
                results = tmdb.search_movie(search_term)
                for r in results[:5]:
                    c1, c2 = st.columns([1, 4])
                    with c1:
                        poster = tmdb.get_poster_url(r.get('poster_path'))
                        if poster:
                            st.image(poster, width=100)
                    with c2:
                        st.write(f"**{r['title']}** ({r.get('release_date', 'N/A')[:4]})")
                        already_original = engine.check_movie_exists(r['id'], links)
                        existing_new = db.get_all_new_movies()
                        already_custom = (not existing_new.empty) and (r['id'] in existing_new['tmdb_id'].values)

                        if already_original:
                            st.info("✅ Already in the original catalog.")
                        elif already_custom:
                            st.info("✅ Already added previously.")
                        else:
                            if st.button("➕ Add This Movie", key=f"add_{r['id']}"):
                                details = tmdb.get_movie_details(r['id'])
                                genres = '|'.join([g['name'] for g in details.get('genres', [])]) or 'Unknown'
                                year = int(r.get('release_date', '0000')[:4]) if r.get('release_date') else None
                                added = db.add_new_movie(
                                    tmdb_id=r['id'], title=r['title'], genres=genres, year=year,
                                    poster_url=tmdb.get_poster_url(r.get('poster_path')), overview=r.get('overview', '')
                                )
                                if added:
                                    st.success(f"Added '{r['title']}' to the catalog!")
                                    st.cache_data.clear()
                                    st.rerun()

            st.divider()
            st.subheader("📋 Movies Added by Admins")
            added_movies = db.get_all_new_movies()
            if added_movies.empty:
                st.info("No custom movies added yet.")
            else:
                st.dataframe(added_movies[['title', 'genres', 'year', 'added_at']], use_container_width=True)

        with tab2:
            st.write("Retrain the recommendation model using all current data (original + new ratings/movies).")
            st.write(f"Current total ratings in system: **{ratings.shape[0]:,}**")
            if st.button("🔄 Retrain Collaborative Filtering Model"):
                with st.spinner("Retraining model..."):
                    new_algo, rmse, mae, total = engine.retrain_model()
                st.success(f"Model retrained on {total:,} ratings. RMSE: {rmse:.3f}, MAE: {mae:.3f}")
                st.cache_resource.clear()

            if st.button("🔄 Retrain Content Similarity Model"):
                with st.spinner("Rebuilding content similarity matrix..."):
                    engine.retrain_content_model()
                st.success("Content similarity model updated with new movies.")
                st.cache_resource.clear()