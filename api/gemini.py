import os
import re
import time
import logging
import requests
from config import Config

logger = logging.getLogger(__name__)

# Exponential backoff retry delays (in seconds) for HTTP 503 High Demand / UNAVAILABLE
RETRY_DELAYS = [2, 4, 8]

TRAVEL_SYSTEM_INSTRUCTION = """You are TravelAI, an advanced AI travel companion assistant.

Key Responsibilities:
- Answer all travel-related questions with accurate, engaging, and practical advice.
- When creating travel itineraries, ALWAYS generate a complete day-by-day plan for the EXACT number of days requested by the traveler.
  * If the user requests 1 day, generate Day 1.
  * If the user requests 4 days, generate Day 1, Day 2, Day 3, and Day 4.
  * If the user requests 5 days, generate Day 1, Day 2, Day 3, Day 4, and Day 5.
  * If the user requests 7 days, generate all 7 days (Day 1 through Day 7).
  * If the user requests 10 days, generate all 10 days (Day 1 through Day 10).
  * If the user requests 15 days, generate all 15 days (Day 1 through Day 15).
  * NEVER truncate, summarize, or default to 3 days unless the user explicitly requested 3 days.
- Organize each day clearly with:
  * Morning (09:00 AM)
  * Afternoon (01:30 PM)
  * Evening (06:00 PM)
- Suggest top attractions, local food specialties, transport tips, and budget guidance.
- Format responses cleanly with Markdown headers and bullet points.
"""

def _is_503_error(e):
    """Detect whether an exception or error represents an HTTP 503 / UNAVAILABLE response."""
    code = getattr(e, 'code', None) or getattr(e, 'status_code', None)
    if code == 503:
        return True

    err_msg = str(e).lower()
    return (
        '503' in err_msg or
        'unavailable' in err_msg or
        'service unavailable' in err_msg or
        'high demand' in err_msg
    )


def _build_contents_from_history(message, history=None):
    contents = []

    if history:
        for item in history:
            contents.append(item)

    contents.append({
        "role": "user",
        "parts": [{"text": message.strip()}]
    })

    return contents


def _ask_via_google_genai_sdk(api_key, model_name, message, history=None):
    """Attempt request using the modern google-genai SDK with exponential backoff on 503."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    contents = _build_contents_from_history(message, history)
    
    config = types.GenerateContentConfig(
        system_instruction=TRAVEL_SYSTEM_INSTRUCTION,
        temperature=0.7,
        max_output_tokens=4000
    )
    
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
            "maxOutputTokens": 4000
        }
    }
    
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


WORD_TO_NUM = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14,
    'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18,
    'nineteen': 19, 'twenty': 20, 'twenty-one': 21, 'thirty': 30
}

KNOWN_DESTINATIONS = [
    'Goa', 'Manali', 'Jaipur', 'Kerala', 'Leh', 'Ladakh', 'Varanasi', 'Ooty',
    'Rishikesh', 'Udaipur', 'Munnar', 'Shimla', 'Darjeeling', 'Agra', 'Andaman',
    'Jaisalmer', 'Hampi', 'Coorg', 'Pondicherry', 'Ranthambore', 'Srinagar',
    'Gokarna', 'Kasol', 'Mahabalipuram', 'Kaziranga', 'Shillong', 'Kanyakumari',
    'Wayanad', 'Mount Abu', 'Pushkar', 'Amritsar', 'Alleppey', 'Spiti', 'Tawang',
    'Aizawl', 'Gangtok', 'Chikmagalur', 'Kutch', 'Khajuraho', 'Bandhavgarh',
    'Bhubaneswar', 'Puri', 'Bhimbetka', 'Lonavala', 'Mahabaleshwar', 'Diu',
    'Guwahati', 'Dharamshala', 'Nainital', 'Mussoorie', 'Bodh Gaya', 'Ajanta',
    'Ellora', 'Kodaikanal', 'Alibaug', 'Dhanushkodi', 'Valparai', 'Madurai',
    'Rameswaram', 'Pachmarhi', 'Orchha', 'Gwalior', 'Majuli', 'Cherrapunji',
    'Dalhousie', 'Khajjiar', 'Auli', 'Chopta', 'Binsar', 'Gulmarg', 'Pahalgam',
    'Sonamarg', 'Varkala', 'Kumarakom', 'Kovalam', 'Bikaner', 'Kumbhalgarh',
    'Bundi', 'Gir', 'Somnath', 'Dwarka', 'Saputara', 'Tirthan', 'Patan',
    'Kanha', 'Pench', 'Tadoba', 'Tarkarli', 'Paris', 'Tokyo', 'Bali', 'Dubai',
    'Bangkok', 'Rome', 'London', 'New York', 'Swiss Alps', 'Switzerland', 'Phuket',
    'Santorini', 'Maldives', 'Barcelona', 'Kyoto', 'Cairo', 'Singapore', 'Istanbul',
    'Reykjavik', 'Cape Town', 'Queenstown', 'Amsterdam', 'Rio', 'Kathmandu',
    'Hanoi', 'Sydney', 'Venice', 'Dubrovnik', 'Prague', 'Vienna', 'Koh Samui'
]

DAY_TEMPLATES = [
    {
        "theme": "Arrival, Orientation & Welcome Stroll",
        "morning": "Check into accommodation, unpack, enjoy breakfast at a popular cafe, and take an orientation walk through the central area.",
        "afternoon": "Explore the historic old town, central monuments, and architectural landmarks to get acquainted with the local vibe.",
        "evening": "Head to a scenic sunset viewpoint or river/coastal promenade, followed by a welcome dinner featuring traditional regional cuisine."
    },
    {
        "theme": "Iconic Heritage Sites & Cultural Landmarks",
        "morning": "Early morning visit to the premier historic fortress, grand temple, or heritage palace before peak crowds arrive.",
        "afternoon": "Guided cultural immersion exploring historic museums, artisan galleries, and ancient architecture.",
        "evening": "Stroll through the illuminated heritage quarter and dine at a renowned local restaurant."
    },
    {
        "theme": "Scenic Nature, Parks & Viewpoint Panoramas",
        "morning": "Fresh air morning walk through botanical gardens, scenic nature trails, or peaceful waterfront promenades.",
        "afternoon": "Panoramic viewpoint excursion, cable car ride, or scenic lake/river boat cruise.",
        "evening": "Relax at a rooftop cafe overlooking the skyline or sunset valley, sampling local beverages and appetizers."
    },
    {
        "theme": "Artisan Markets, Street Food & Local Crafts",
        "morning": "Visit bustling morning bazaars and farmers' markets for photography and authentic local snacks.",
        "afternoon": "Guided culinary food crawl sampling street delicacies, followed by browsing handicraft workshops.",
        "evening": "Leisurely dinner at a beloved neighborhood eatery followed by exploring vibrant evening markets."
    },
    {
        "theme": "Adventure, Trekking & Scenic Excursions",
        "morning": "Morning outdoor adventure (nature trek, water sports, cycling tour, or mountain ridge hike).",
        "afternoon": "Scenic picnic lunch followed by exploring nearby waterfalls, caves, or viewpoints.",
        "evening": "Comfort food dinner at a rustic cafe, unwinding after an active day outdoors."
    },
    {
        "theme": "Historic Quarters & Hidden Gems",
        "morning": "Self-guided walking tour through colorful residential quarters and lesser-known historical alleys.",
        "afternoon": "Visit regional art galleries, boutique craft studios, and contemporary cultural spaces.",
        "evening": "Sunset stroll along the promenade or plaza, followed by dinner with live acoustic music."
    },
    {
        "theme": "Day Trip Excursion to Surrounding Highlights",
        "morning": "Scenic day trip to nearby countryside villages, historic fortresses, or scenic natural landscapes.",
        "afternoon": "In-depth exploration of the day-trip destination with lunch at a countryside tavern.",
        "evening": "Return to base, relax, and enjoy dinner featuring regional comfort food."
    },
    {
        "theme": "Museums, Heritage Galleries & Architecture",
        "morning": "Visit the central city museum and contemporary art exhibits.",
        "afternoon": "Architectural walking tour exploring iconic buildings, courtyards, and scenic gardens.",
        "evening": "Dinner at a fine dining restaurant celebrating modern culinary twists on traditional recipes."
    },
    {
        "theme": "Spiritual Havens, Gardens & Tranquility",
        "morning": "Peaceful morning visit to serene temples, monasteries, or historic spiritual shrines.",
        "afternoon": "Relaxing afternoon at a lush botanical conservatory or tranquil tea garden / park.",
        "evening": "Riverside or lakeside evening walk, watching traditional rituals or enjoying a peaceful twilight."
    },
    {
        "theme": "Local Workshops, Photography & Coffee Culture",
        "morning": "Photography walk catching golden hour light across iconic landmarks.",
        "afternoon": "Participate in a local cooking workshop, pottery class, or artisanal coffee tasting.",
        "evening": "Dinner at a garden terrace restaurant with local specialties and desserts."
    },
    {
        "theme": "Coastal / Mountain Ridge Exploration",
        "morning": "Excursion to stunning coastal coves or elevated mountain ridges with panoramic lookouts.",
        "afternoon": "Seafood / alpine mountain lunch, followed by relaxing along scenic nature viewpoints.",
        "evening": "Stargazing or twilight campfire / sunset lounge with refreshing regional drinks."
    },
    {
        "theme": "Vintage Bazaars & Contemporary Lifestyle",
        "morning": "Explore flea markets, vintage antique stores, and independent bookstore cafes.",
        "afternoon": "Leisurely lunch followed by visit to modern entertainment districts or waterfront plazas.",
        "evening": "Dinner at a lively dining venue with cultural dance or musical performances."
    },
    {
        "theme": "Wellness Retreat & Pampering Day",
        "morning": "Indulgent morning yoga session or holistic wellness massage treatment.",
        "afternoon": "Light organic lunch, relaxing poolside or in quiet garden reading spots.",
        "evening": "Sunset relaxation followed by an intimate candle-lit dinner."
    },
    {
        "theme": "Memorable Highlights & Farewell Dinner",
        "morning": "Revisit your favorite spot in town or pick up artisanal souvenirs and local spices/sweets.",
        "afternoon": "Last scenic walk, packing, and enjoying an afternoon tea/dessert break.",
        "evening": "Grand celebration farewell dinner at the destination's top-rated restaurant, toast to an unforgettable trip!"
    }
]


def _extract_requested_days(message):
    """
    Extracts the number of itinerary days requested by the traveler.
    Defaults to 3 only if no specific duration is specified in the message.
    """
    m = message.lower()
    
    # 1. Match numeric digits followed by day(s): e.g. "5 days", "7-day", "10days", "4 day"
    num_match = re.search(r'\b(\d{1,2})\s*-?\s*days?\b', m)
    if num_match:
        val = int(num_match.group(1))
        if 1 <= val <= 30:
            return val

    # 2. Match "for/plan <number> days": e.g. "plan for 5 days"
    day_num = re.search(r'\b(?:for|of|plan)\s*(\d{1,2})\s*days?\b', m)
    if day_num:
        val = int(day_num.group(1))
        if 1 <= val <= 30:
            return val

    # 3. Match word numbers followed by day(s): e.g. "five days", "seven-day", "two days"
    word_pattern = r'\b(' + '|'.join(WORD_TO_NUM.keys()) + r')\s*-?\s*days?\b'
    word_match = re.search(word_pattern, m)
    if word_match:
        word = word_match.group(1)
        return WORD_TO_NUM.get(word, 3)

    # 4. Common colloquial duration expressions
    if 'two weeks' in m or '2 weeks' in m:
        return 14
    if 'a week' in m or '1 week' in m or 'one week' in m:
        return 7
    if 'weekend' in m:
        return 2

    return 3


_ALL_DESTINATIONS = None

def _get_known_destinations():
    global _ALL_DESTINATIONS
    if _ALL_DESTINATIONS is not None:
        return _ALL_DESTINATIONS
    
    dest_set = set(KNOWN_DESTINATIONS)
    try:
        csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'datasets', 'destinations.csv')
        if os.path.exists(csv_path):
            import pandas as pd
            df = pd.read_csv(csv_path)
            for name in df['name'].dropna():
                clean_name = name.split('(')[0].strip()
                if clean_name:
                    dest_set.add(clean_name)
                dest_set.add(name.strip())
    except Exception:
        pass
    
    _ALL_DESTINATIONS = sorted(list(dest_set), key=lambda x: -len(x))
    return _ALL_DESTINATIONS


def _extract_destination(message):
    """
    Detects the destination name from the user's message.
    """
    m_lower = message.lower()
    
    # 1. Match known destinations from dataset
    for dest in _get_known_destinations():
        pattern = r'\b' + re.escape(dest.lower()) + r'\b'
        if re.search(pattern, m_lower):
            return dest
            
    # 2. Match preposition patterns after stripping duration (e.g. "for 3 days", "5-day")
    cleaned = re.sub(r'\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*-?\s*days?\b', '', message, flags=re.I)
    prep_match = re.search(r'\b(?:in|to|for|around|visit|visiting)\s+([A-Za-z\s]{3,25})', cleaned)
    if prep_match:
        cand = prep_match.group(1).strip()
        cand = re.sub(r'\b(?:a|the|my|our|trip|itinerary|plan|vacation)\b', '', cand, flags=re.I).strip()
        if len(cand) >= 3:
            return cand.title()
            
    return "Your Destination"


def _generate_fallback_itinerary(num_days, destination):
    """
    Generates a complete day-by-day itinerary covering exactly num_days.
    """
    dest_title = destination.strip().title() if destination else "Your Destination"
    lines = [f"### 🗺️ Custom {num_days}-Day Travel Itinerary for {dest_title}\n"]
    
    for day_idx in range(1, num_days + 1):
        tpl_idx = (day_idx - 1) % len(DAY_TEMPLATES)
        tpl = DAY_TEMPLATES[tpl_idx]
        
        lines.append(f"* **Day {day_idx}: {tpl['theme']}**")
        lines.append(f"  - *Morning (09:00 AM)*: {tpl['morning']}")
        lines.append(f"  - *Afternoon (01:30 PM)*: {tpl['afternoon']}")
        lines.append(f"  - *Evening (06:00 PM)*: {tpl['evening']}\n")
        
    lines.append("> 💡 *Tip: For dynamic, fully personalized AI itineraries tailored to any destination, please ensure `GEMINI_API_KEY` is added to your `.env` file.*")
    return "\n".join(lines)


def _generate_fallback_travel_reply(message):
    """
    Returns an informative travel-focused response when Gemini API key is missing or offline.
    Dynamically generates itineraries matching the exact number of days requested.
    """
    m_lower = message.lower()
    
    if any(k in m_lower for k in ['itinerary', 'plan', 'days', 'day', 'trip']):
        num_days = _extract_requested_days(message)
        destination = _extract_destination(message)
        return _generate_fallback_itinerary(num_days, destination)
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
            "* 📅 **Day-by-Day Itineraries**: Custom morning-to-night trip schedules for any number of days.\n"
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
    model_name = Config.GEMINI_MODEL or os.environ.get(
        "GEMINI_MODEL",
        "gemini-2.5-flash"
    )

    if not message or not message.strip():
        return "Please ask a question about your travel plans, destinations, or itineraries!"
        
    if not api_key:
        logger.info("GEMINI_API_KEY not configured. Using TravelAI assistant offline fallback mode.")
        return _generate_fallback_travel_reply(message)

    # If user requests an itinerary, reinforce the requested days in the prompt
    clean_msg = message.strip()
    m_lower = clean_msg.lower()
    if any(k in m_lower for k in ['itinerary', 'plan', 'days', 'day']):
        num_days = _extract_requested_days(clean_msg)
        reinforced_msg = f"{clean_msg}\n\n[Please generate a complete day-by-day plan covering all {num_days} days from Day 1 to Day {num_days}.]"
    else:
        reinforced_msg = clean_msg

    # 1. Try official google-genai SDK
    try:
        reply = _ask_via_google_genai_sdk(api_key, model_name, reinforced_msg, history)
        if reply:
            return reply
    except Exception as e:
        logger.warning(f"google-genai SDK invocation encountered issue: {e}. Trying REST fallback...")

    # 2. Try direct REST API fallback
    try:
        reply = _ask_via_rest_api(api_key, model_name, reinforced_msg, history)
        if reply:
            return reply
    except Exception as e:
        logger.error(f"Gemini REST invocation failed: {e}")

    # 3. Fallback to dynamic travel reply generator
    return _generate_fallback_travel_reply(message)
