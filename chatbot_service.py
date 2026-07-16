import os
os.environ["PYTHONIOENCODING"] = "utf-8"



from groq import Groq

import streamlit as st
GROQ_API_KEY = st.secrets["GROQ_API_KEY"]

client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """You are the AI assistant for MovieMind, a movie recommendation platform.
You help users discover movies, discuss films, explain genres, and give recommendations.

IMPORTANT - Catalog awareness: You will be given a list of movies found in our catalog
relevant to the user's message. Trust this list completely - if a movie appears there, it
IS in our catalog. Only say a movie is "not in our catalog" if it genuinely does not appear
in the provided list AND is clearly unrelated to the search terms.

IMPORTANT - Personalization: If you are told the user has already seen a movie, start your
reply by mentioning that. If a star rating is included, say "You've already watched this one
— you rated it X/5 stars." If no rating is included (only saved to watchlist), say "You've
already added this one to your watchlist before." Either way, follow up with "Here's the
story in case you forgot:" and a brief plot summary in your own words, based on the story
summary provided to you.

Keep answers friendly, concise, and focused on movies."""

def get_chat_response(user_message, chat_history, catalog_context=""):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if catalog_context:
        messages.append({"role": "system", "content": f"Context for this message:\n{catalog_context}"})
    messages.extend(chat_history)
    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.7,
        max_tokens=500
    )
    return response.choices[0].message.content