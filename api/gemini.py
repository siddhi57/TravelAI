import os
import time
import logging
import requests
from config import Config

logger = logging.getLogger(__name__)

# Exponential backoff retry delays (in seconds) for HTTP 503 High Demand / UNAVAILABLE
RETRY_DELAYS = [2, 4, 8]

TRAVEL_SYSTEM_INSTRUCTION = (
    "You are the TravelAI Companion Assistant, a friendly, knowledgeable, and reliable AI travel guide. "
    "Your mission is to help travelers discover wonderful destinations, build realistic day-by-day itineraries, "
    "find attractions, choose hotels and budget tiers, learn the best times to visit, get packing suggestions, "
    "and explore local cuisine and culture.\n\n"
    "Guidelines:\n"
    "1. Structure answers clearly using markdown formatting (bullet points, bold highlights, concise paragraphs).\n"
    "2. For itineraries, organize by Morning, Afternoon, and Evening with practical transit notes.\n"
    "3. Keep tone positive, inspiring, and travel-focused.\n"
    "4. If a user asks about non-travel topics, answer briefly or politely pivot back to travel and vacation planning.\n"
    "5. Remind users of TravelAI features when relevant (AI Recommender, Hotels Finder, Live Weather, Attractions Map, Itinerary Planner)."
)

def _is_503_error(e):
    """Detect whether an exception or error represents an HTTP 503 / UNAVAILABLE response."""
    code = getattr(e, 'code', None) or getattr(e, 'status_code', None)
    if code == 503:
        return True
    err_msg = str(e).lower()
    return '503' in err_msg or 'unavailable' in err_msg or 'high demand' in err_msg or 'overloaded' in err_msg

def _build_contents_from_history(message, history=None):
    """
    Normalizes rolling chat history into the Gemini format.
    Accepts history as a list of dicts: [{'role': 'user'|'model'|'assistant', 'text': '...'}]
    """
    contents = []
    if history and isinstance(history, list):
        # Limit to the last 10 turns to avoid excessive token consumption
        for item in history[-10:]:
            role = item.get('role', 'user')
            # Normalize 'assistant' or 'bot' to 'model' for Gemini
            if role in ('assistant', 'bot'):
                role = 'model'
            elif role != 'model':
                role = 'user'
            text = item.get('text', '').strip()
            if text:
                contents.append({
                    'role': role,
                    'parts': [{'text': text}]
                })
                
    # Append the current prompt
    contents.append({
        'role': 'user',
        'parts': [{'text': message.strip()}]
    })
    return contents

def _ask_via_google_genai_sdk(api_key, model_name, message, history=None):
    """Attempt request using the modern google-genai SDK."""
    """Attempt request using the modern google-genai SDK with exponential backoff on 503."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    contents = _build_contents_from_history(message, history)
    
    config = types.GenerateContentConfig(
        system_instruction=TRAVEL_SYSTEM_INSTRUCTION,
        temperature=0.7,
        max_output_tokens=1500
    )
    
    response = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=config
    )
    if response and response.text:
        return response.text
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config
            )
            if response and response.text:
                return response.text
            return None
        except Exception as e:
            if _is_503_error(e) and attempt < len(RETRY_DELAYS):
                delay = RETRY_DELAYS[attempt]
                logger.warning(f"Gemini SDK 503 high demand received. Retrying in {delay}s (attempt {attempt + 1}/{len(RETRY_DELAYS)})...")
                time.sleep(delay)
                continue
            raise e
    return None

def _ask_via_rest_api(api_key, model_name, message, history=None):
    """Direct REST fallback to Generative Language API."""
    """Direct REST fallback to Generative Language API with exponential backoff on 503."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    contents = _build_contents_from_history(message, history)
    
    payload = {
        "contents": contents,
        "systemInstruction": {
            "parts": [{"text": TRAVEL_SYSTEM_INSTRUCTION}]
        },
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1500
        }
    }
    
    resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts and "text" in parts[0]:
                return parts[0]["text"]
    else:
        logger.warning(f"Gemini REST error {resp.status_code}: {resp.text}")
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        return parts[0]["text"]
                return None
            elif resp.status_code == 503:
                if attempt < len(RETRY_DELAYS):
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(f"Gemini REST 503 high demand received. Retrying in {delay}s (attempt {attempt + 1}/{len(RETRY_DELAYS)})...")
                    time.sleep(delay)
                    continue
                else:
                    logger.warning("Gemini REST 503: Maximum retries (3) reached.")
                    return None
            else:
                logger.warning(f"Gemini REST error {resp.status_code}: {resp.text}")
                return None
        except requests.RequestException as e:
            if attempt < len(RETRY_DELAYS):
                delay = RETRY_DELAYS[attempt]
                logger.warning(f"Gemini REST request error: {e}. Retrying in {delay}s (attempt {attempt + 1}/{len(RETRY_DELAYS)})...")
                time.sleep(delay)
                continue
            return None
    return None

def _generate_fallback_travel_reply(message):
    """
    Returns an informative travel-focused response when Gemini API key is missing or offline.
    """
    m_lower = message.lower()
    
    if any(k in m_lower for k in ['itinerary', 'plan', 'days', 'day']):
        return (
            "### 🗺️ Sample 3-Day Travel Itinerary\n\n"
            "* **Day 1: Arrival & Historic Landmark Exploration**\n"
            "  - *Morning*: Check into hotel, breakfast at a local cafe, orientation walk.\n"
            "  - *Afternoon*: Visit the central heritage sites or famous fortress.\n"
            "  - *Evening*: Sunset viewpoint followed by dinner at a traditional local restaurant.\n\n"
            "* **Day 2: Cultural Immersion & Scenic Nature**\n"
            "  - *Morning*: Early visit to botanical gardens or waterfront promenades.\n"
            "  - *Afternoon*: Regional museums, cultural bazaars, and local artisan markets.\n"
            "  - *Evening*: Leisurely stroll and local culinary sampling.\n\n"
            "* **Day 3: Adventure & Departure**\n"
            "  - *Morning*: Outdoor excursion or scenic viewpoint photography.\n"
            "  - *Afternoon*: Souvenir shopping and cafe relaxation.\n"
            "  - *Evening*: Return journey.\n\n"
            "> 💡 *Tip: For dynamic, fully personalized AI itineraries tailored to any destination, please ensure `GEMINI_API_KEY` is added to your `.env` file.*"
        )
    elif any(k in m_lower for k in ['pack', 'packing', 'carry']):
        return (
            "### 🎒 Travel Packing Essentials Checklist\n\n"
            "* **Documents**: Passport / ID, booking confirmations, emergency contact cards, travel insurance.\n"
            "* **Electronics**: Universal travel adapter, power bank, fast charging cables, noise-cancelling headphones.\n"
            "* **Clothing**: Versatile layers, breathable walking shoes, rain jacket / light windbreaker, sunglasses.\n"
            "* **Health & Hygiene**: Prescribed meds, hand sanitizer, sunblock (SPF 50+), hydration electrolytes, mini first-aid kit.\n\n"
            "> 💡 *Tip: You can ask me specific questions for beach trips, winter mountain packing, or international travel when `GEMINI_API_KEY` is enabled in `.env`!*"
        )
    elif any(k in m_lower for k in ['weather', 'best time', 'season', 'when to visit']):
        return (
            "### ☀️ Best Time to Visit Insights\n\n"
            "* **Spring / Autumn (Peak Comfort)**: Generally ideal for pleasant sightseeing, moderate crowds, and mild outdoor temperatures.\n"
            "* **Winter**: Perfect for tropical coastlines and heritage sightseeing; or snow sports in alpine mountain regions.\n"
            "* **Monsoon / Off-Season**: Great for lush landscapes, budget-friendly hotels, and tranquility, with intermittent rain showers.\n\n"
            "> 💡 *Check out the **Live Weather** tab in the top navigation to see current temperature and 5-day forecasts for any destination!*"
        )
    else:
        return (
            "### 👋 Hello from TravelAI Companion!\n\n"
            "I'm here to assist you with all your travel planning needs. Here are a few things I can do for you:\n\n"
            "* 🏝️ **Recommend Destinations**: Matching your budget, interests, and preferred season.\n"
            "* 📅 **Day-by-Day Itineraries**: Custom morning-to-night trip schedules.\n"
            "* 🏨 **Hotels & Accommodations**: Guidance on budget, moderate, and luxury stays.\n"
            "* 🎒 **Packing Advice**: Tailored lists for beaches, mountains, or city walks.\n"
            "* 🍜 **Culinary & Culture**: Signature dishes and local etiquette to know before you go.\n\n"
            "> ℹ️ *Note: I am currently running in offline fallback mode. To enable real-time Gemini AI intelligence, configure `GEMINI_API_KEY` in your `.env` file.*"
        )

def ask_travel_gemini(message, history=None):
    """
    Main entry point for travel questions.
    Attempts generation via google-genai SDK first, falls back to direct REST,
    and returns a graceful travel assistant response if credentials are not configured.
    """
    api_key = Config.GEMINI_API_KEY or os.environ.get('GEMINI_API_KEY', '')
    model_name = Config.GEMINI_MODEL or os.environ.get('GEMINI_MODEL', 'gemini-3.8-flash')
    
    if not message or not message.strip():
        return "Please ask a question about your travel plans, destinations, or itineraries!"
        
    if not api_key:
        logger.info("GEMINI_API_KEY not configured. Using TravelAI assistant offline fallback mode.")
        return _generate_fallback_travel_reply(message)

    # 1. Try official google-genai SDK
    try:
        reply = _ask_via_google_genai_sdk(api_key, model_name, message, history)
        if reply:
            return reply
    except Exception as e:
        logger.warning(f"google-genai SDK invocation encountered issue: {e}. Trying REST fallback...")

    # 2. Try direct REST API fallback
    try:
        reply = _ask_via_rest_api(api_key, model_name, message, history)
        if reply:
            return reply
    except Exception as e:
        logger.error(f"Gemini REST invocation failed: {e}")

    # 3. Fallback on network timeout or unexpected error
    return _generate_fallback_travel_reply(message)
