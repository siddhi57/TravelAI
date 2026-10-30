import os
import re
import time
import logging
import requests
import pandas as pd
from config import Config

logger = logging.getLogger(__name__)

# Exponential backoff retry delays (in seconds) for HTTP 503 High Demand / UNAVAILABLE
RETRY_DELAYS = [2, 4, 8]

BASE_SYSTEM_INSTRUCTION = """You are TravelAI, an advanced, highly personalized AI travel companion and expert concierge assistant.

Core Responsibilities:
1. Provide personalized, engaging, accurate, and deeply insightful travel assistance across the entire journey—including destination discovery, authentic local cuisine, transit and logistics, realistic budget estimation, safety and solo travel, weather and packing, cultural etiquette, hidden offbeat spots, and day-by-day itineraries.
2. For Day-by-Day Itineraries (When Explicitly Requested):
   - ALWAYS generate a complete day-by-day plan for the EXACT number of days requested by the traveler (Day 1 through Day N).
   - NEVER truncate, summarize, or default to 3 days unless the user explicitly requested 3 days.
   - Organize each day clearly with:
     * Morning (09:00 AM)
     * Afternoon (01:30 PM)
     * Evening (06:00 PM)
   - Include realistic transit times, signature local dishes, and practical tips for each day.
3. For Other Travel Queries:
   - Food & Dining: Recommend iconic signature dishes, street food hubs, beloved local cafes/dhabas, and dietary advice (pure veg, vegan, jain, halal).
   - Transportation & Commute: Explain how to get from city to city and around towns (trains, Vande Bharat, sleeper Volvo buses, flights, rented scooters, app cabs, ferries), typical fares, and transit tips.
   - Budget & Cost Estimates: Provide transparent pricing estimates in INR (₹) across our 3 budget tiers (Budget under ₹15,000, Moderate ₹15,000-₹50,000, Luxury above ₹50,000). Never use dollar ($) symbols.
   - Safety & Solo Travel: Share practical, reassuring advice for solo and female travelers, safe neighborhoods, emergency helplines (112 / 1091), and how to avoid tourist scams.
   - Packing & Weather: Provide weather-specific, practical packing checklists (winter/snow, beach, monsoon, high-altitude trekking).
   - Culture & Etiquette: Explain temple dress codes, shoe/leather restrictions, tipping customs, and respectful photography.
   - Adventure & Outdoor Activities: Details on trekking routes, water sports, paragliding, river rafting, scuba diving, difficulty levels, and best seasons.
   - Offbeat & Hidden Gems: Highlight peaceful, lesser-known alternatives to crowded tourist hubs.
4. Tone & Personalization:
   - Warm, enthusiastic, empathetic, and culturally aware.
   - Address the traveler warmly by their name when known.
   - Format cleanly with Markdown headers (###), bold text, and bullet points.
   - Conclude with a helpful, context-relevant follow-up prompt or suggestion to keep the traveler inspired and engaged.
"""

def get_system_instruction(user_name=None, context=None):
    """Builds a personalized system instruction incorporating traveler identity and page context."""
    instruction = BASE_SYSTEM_INSTRUCTION
    if user_name:
        instruction += f"\n\nTraveler Context: You are currently assisting {user_name}. Greet and address them warmly by name."
    if context and isinstance(context, dict):
        dest = context.get('destination')
        page = context.get('url') or context.get('page')
        if dest:
            instruction += f"\nCurrent Destination Context: The traveler is currently viewing or inquiring about {dest}."
        if page:
            instruction += f"\nCurrent Page Context: {page}"
    return instruction


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


def _ask_via_google_genai_sdk(api_key, model_name, message, history=None, user_name=None, context=None):
    """Attempt request using the modern google-genai SDK with exponential backoff on 503."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    contents = _build_contents_from_history(message, history)
    system_instruction = get_system_instruction(user_name=user_name, context=context)
    
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
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


def _ask_via_rest_api(api_key, model_name, message, history=None, user_name=None, context=None):
    """Direct REST fallback to Generative Language API with exponential backoff on 503."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    contents = _build_contents_from_history(message, history)
    system_instruction = get_system_instruction(user_name=user_name, context=context)
    
    payload = {
        "contents": contents,
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
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
    'Hanoi', 'Sydney', 'Venice', 'Dubrovnik', 'Prague', 'Vienna', 'Koh Samui',
    'Delhi', 'Mumbai', 'Kolkata', 'Bangalore', 'Chennai', 'Hyderabad'
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

_ALL_DESTINATIONS = None
_DESTINATIONS_DF = None

def _get_destinations_dataframe():
    global _DESTINATIONS_DF
    if _DESTINATIONS_DF is not None:
        return _DESTINATIONS_DF
    try:
        csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'datasets', 'destinations.csv')
        if os.path.exists(csv_path):
            _DESTINATIONS_DF = pd.read_csv(csv_path)
            return _DESTINATIONS_DF
    except Exception:
        pass
    return None


def _get_known_destinations():
    global _ALL_DESTINATIONS
    if _ALL_DESTINATIONS is not None:
        return _ALL_DESTINATIONS
    
    dest_set = set(KNOWN_DESTINATIONS)
    df = _get_destinations_dataframe()
    if df is not None:
        for name in df['name'].dropna():
            clean_name = str(name).split('(')[0].strip()
            if clean_name:
                dest_set.add(clean_name)
            dest_set.add(str(name).strip())
    
    _ALL_DESTINATIONS = sorted(list(dest_set), key=lambda x: -len(x))
    return _ALL_DESTINATIONS


def _lookup_destination_record(dest_name):
    """Retrieves dataset attributes (state, category, budget_level, description, tags) for a destination."""
    if not dest_name:
        return None
    df = _get_destinations_dataframe()
    if df is None:
        return None
    clean = dest_name.strip().lower()
    matches = df[df['name'].str.strip().str.lower() == clean]
    if not matches.empty:
        return matches.iloc[0].to_dict()
    # Partial match
    partial = df[df['name'].str.strip().str.lower().str.contains(clean, regex=False)]
    if not partial.empty:
        return partial.iloc[0].to_dict()
    return None


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


def _extract_destination(message, context=None):
    """Detects the destination name from the message or active context."""
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

    # 3. Fallback to destination present in context
    if context and isinstance(context, dict) and context.get('destination'):
        return context.get('destination').strip().title()
            
    return None


def _is_itinerary_request(message):
    """
    Carefully determines whether the traveler is explicitly asking for a day-by-day travel itinerary
    versus other travel-related inquiries (food, safety, packing, transit, budget, etc.).
    """
    m = message.lower().strip()
    
    # Negative checks: if user is specifically asking about other things without explicitly saying "itinerary"
    other_topics = [
        'food', 'street food', 'cuisine', 'eat', 'restaurant', 'cafe', 'dish', 'dishes',
        'safe', 'safety', 'solo', 'female', 'woman',
        'how to reach', 'how to travel from', 'train', 'flight', 'bus', 'scooter', 'cab', 'taxi', 'commute',
        'what to pack', 'packing', 'carry', 'clothes',
        'best time of day', 'best time to visit', 'when to visit', 'weather', 'climate',
        'dress code', 'temple rule', 'etiquette', 'tipping', 'customs',
        'budget hack', 'how much money', 'cost of trip', 'under 15000', 'cheap trip'
    ]
    has_other_topic = any(topic in m for topic in other_topics)

    # Strong explicit itinerary terms
    if 'itinerary' in m or 'day-by-day' in m or 'day by day' in m:
        return True

    # If it has another topic and doesn't explicitly mention itinerary, it's that topic!
    if has_other_topic and 'itinerary' not in m:
        return False

    # Duration + plan/trip/tour patterns: e.g. "7 days plan for Goa", "4-day trip plan for Manali", "5 days in Goa"
    duration_plan_patterns = [
        r'\b\d+\s*-?\s*days?\s+(?:trip\s+)?plan\b',
        r'\b\d+\s*-?\s*days?\s+(?:in|for|around)\s+[a-z\s]+',
        r'\b(?:plan|trip)\s+for\s+\d+\s+days\b',
        r'\b(?:one|two|three|four|five|six|seven|eight|nine|ten)\s*-?\s*days?\s+(?:trip\s+)?plan\b',
        r'\b\d+\s*-?\s*days?\s+schedule\b'
    ]
    for pattern in duration_plan_patterns:
        if re.search(pattern, m):
            return True

    return False


def _generate_fallback_itinerary(num_days, destination, user_name=None):
    """Generates a complete day-by-day itinerary covering exactly num_days."""
    dest_title = destination.strip().title() if destination else "Your Destination"
    prefix = f"Hello {user_name}! " if user_name else ""
    lines = [
        f"{prefix}Here is your custom **{num_days}-day travel itinerary** for **{dest_title}**:\n",
        f"### 🗺️ Custom {num_days}-Day Travel Itinerary for {dest_title}\n"
    ]
    
    for day_idx in range(1, num_days + 1):
        tpl_idx = (day_idx - 1) % len(DAY_TEMPLATES)
        tpl = DAY_TEMPLATES[tpl_idx]
        
        lines.append(f"* **Day {day_idx}: {tpl['theme']}**")
        lines.append(f"  - *Morning (09:00 AM)*: {tpl['morning']}")
        lines.append(f"  - *Afternoon (01:30 PM)*: {tpl['afternoon']}")
        lines.append(f"  - *Evening (06:00 PM)*: {tpl['evening']}\n")
        
    lines.append(f"> 💡 *Personalized Tip: Would you like me to recommend top dining spots, transit options, or budget estimates for {dest_title}?*")
    return "\n".join(lines)


# --- SPECIALIZED TRAVEL QUERY GENERATORS (OFFLINE / FALLBACK) ---

DESTINATION_FOOD_SPECIALTIES = {
    'jaipur': {
        'specialties': 'Pyaaz Kachori, Dal Baati Churma, Ker Sangri, Laal Maas, and Ghewar',
        'spots': 'Rawat Mishtan Bhandar (for kachoris), Laxmi Mishtan Bhandar (LMB for sweets & thali), Lassiwala on MI Road, Tapri The Tea House',
        'tip': 'Do not miss the rich saffron lassi served in traditional earthen clay kulhads on MI Road!'
    },
    'goa': {
        'specialties': 'Goan Fish Curry Thali, Prawn Balchão, Pork Vindaloo, Bebinca, Poi bread, and freshly grilled calamari',
        'spots': 'Fisherman\'s Wharf (Cavelossim), Martin\'s Corner (Betalbatim), Vinayak Family Restaurant (Assagao), and Gunpowder (Assagao)',
        'tip': 'Opt for local beach shacks during afternoon lunch for fresh catch-of-the-day at very affordable rates.'
    },
    'manali': {
        'specialties': 'Himachali Siddu with melted desi ghee, river trout fish, Babru, Tudkiya Bhath, and warm spiced apple cider',
        'spots': 'Johnson\'s Cafe (famous wood-fired trout), Cafe 1947 in Old Manali, Drifters\' Cafe, and local dhabas along Mall Road',
        'tip': 'Head to Old Manali along the Manalsu river for bohemian cafes with live acoustic music and artisanal coffee.'
    },
    'kerala': {
        'specialties': 'Appam with vegetable/chicken stew, Malabar Fish Curry, Karimeen Pollichathu (pearl spot in banana leaf), and warm Pazham Pori',
        'spots': 'Paragon Restaurant (Kozhikode/Kochi for biryani), Dhe Puttu (Kochi), and scenic backwater toddy shops for authentic spicy curries',
        'tip': 'Pair Kerala banana chips fried fresh in pure coconut oil with a hot glass of spiced chai during evening strolls.'
    },
    'delhi': {
        'specialties': 'Chole Bhature, Butter Chicken, Paranthas in Paranthe Wali Gali, Dahi Bhalle, and Seekh Kebabs',
        'spots': 'Sita Ram Diwan Chand (Paharganj), Daryaganj Restaurant, Karim\'s (near Jama Masjid), Natraj Dahi Bhalle (Chandni Chowk)',
        'tip': 'Visit Old Delhi early in the morning for freshly fried jalebis and bedmi puri before crowds peak.'
    },
    'mumbai': {
        'specialties': 'Vada Pav, Pav Bhaji, Bombay Sandwich, Bun Maska with Irani Chai, and coastal Malvani seafood',
        'spots': 'Ashok Vada Pav (Kirti College), Sardar Refreshments (Tardeo), Kyani & Co. (Marine Lines), and Gajalee (Vile Parle)',
        'tip': 'Enjoy a piping hot plate of buttery Pav Bhaji at Juhu Beach while catching the Arabian Sea sunset.'
    },
    'varanasi': {
        'specialties': 'Kachori Jalebi breakfast, Tamatar Chaat, Malaiyyo (frothy winter dessert), and authentic Banarasi Meetha Paan',
        'spots': 'Ram Bhandar (Thatheri Bazaar), Kashi Chaat Bhandar (Godowlia), Blue Lassi Shop, and Rajan Paan',
        'tip': 'Start your morning with piping hot kachoris and crisp jalebis right after the sunrise boat ride along Dashashwamedh Ghat.'
    },
    'udaipur': {
        'specialties': 'Dal Baati Churma, Gatte ki Sabzi, Mirchi Vada, and royal Mewari thali',
        'spots': 'Krishna Dal Bati Restro, Ambrai (waterside fine dining overlooking City Palace), and Jagdish Mishtan Bhandar',
        'tip': 'Reserve a sunset table by Lake Pichola for breathtaking reflections of the illuminated City Palace.'
    },
    'ladakh': {
        'specialties': 'Thukpa noodle soup, steamed Momos, Tingmo bread, butter tea (Gur Gur Chai), and Skyu traditional pasta stew',
        'spots': 'Alchi Kitchen (traditional Ladakhi cuisine), The Tibetan Kitchen (Leh), and Gesmo Restaurant (Leh)',
        'tip': 'Sip warm sea-buckthorn juice or butter tea to keep yourself hydrated and acclimatized to high altitudes.'
    },
    'amritsar': {
        'specialties': 'Amritsari Stuffed Kulcha with spicy chole, Guru ka Langar at Golden Temple, Makki di Roti with Sarson da Saag, and rich Lassi',
        'spots': 'Bhai Kulwant Singh Kulchian Wale, Kesar Da Dhaba (since 1916), Ahuja Lassi, and Beera Chicken House',
        'tip': 'Visiting the community kitchen (Langar) at Sri Harmandir Sahib is a deeply humbling and soul-nourishing experience.'
    }
}


def _generate_food_reply(destination, message, user_name=None):
    """Generates authentic dining, cuisine, and street food recommendations."""
    prefix = f"Hello {user_name}! " if user_name else ""
    dest_key = destination.strip().lower() if destination else None
    
    if dest_key and dest_key in DESTINATION_FOOD_SPECIALTIES:
        info = DESTINATION_FOOD_SPECIALTIES[dest_key]
        return (
            f"{prefix}Here is your curated culinary guide to **{destination.title()}**:\n\n"
            f"### 🍲 Must-Try Signature Dishes & Delicacies\n"
            f"* **Signature Specialties**: {info['specialties']}.\n"
            f"* **Famous Food Hubs & Eateries**: {info['spots']}.\n"
            f"* **Foodie Insider Tip**: {info['tip']}\n\n"
            f"### 💰 Approximate Dining Costs\n"
            f"* **Street Food & Snacks**: ₹80 – ₹200 per person\n"
            f"* **Authentic Thali / Mid-tier Restaurant**: ₹250 – ₹550 per person\n"
            f"* **Heritage / Waterfront Fine Dining**: ₹900 – ₹2,200 per person\n\n"
            f"> 💡 *Would you like me to map out top cafes nearby or check live weather for your food walks?*"
        )
    
    rec = _lookup_destination_record(destination) if destination else None
    dest_name = rec['name'] if rec else (destination.title() if destination else "your destination")
    state_str = f" in {rec['state']}" if rec and rec.get('state') else ""
    
    return (
        f"{prefix}Here are authentic culinary and dining recommendations for **{dest_name}**{state_str}:\n\n"
        f"### 🍽️ Signature Regional Flavors & Food Tips\n"
        f"* **Local Specialties**: Seek out traditional regional thalis, seasonal harvest specialties, and freshly made local breads and sweets.\n"
        f"* **Street Food Culture**: Explore central bazaars between 05:00 PM and 08:30 PM when local chaat, savory fritters, and dessert stalls are active.\n"
        f"* **Dietary Options**: Most local eateries happily cater to Pure Vegetarian, Jain, and Vegan dietary requirements upon request.\n\n"
        f"### 💡 Practical Dining Advice\n"
        f"* **Hygiene**: Choose bustling eateries with high footfall where ingredients are cooked fresh right in front of you.\n"
        f"* **Hydration**: Always drink filtered or sealed bottled water, especially when exploring vibrant street markets.\n"
        f"* **Cost Guidelines**: Street bites range from ₹60–₹180, comfortable cafes around ₹350–₹700 per meal.\n\n"
        f"> 💡 *Tell me if you have any dietary preferences (vegetarian, non-vegetarian, spicy, mild) so I can tailor specific spots!*"
    )


def _generate_transport_reply(destination, message, user_name=None):
    """Provides practical transportation and route guidance."""
    prefix = f"Hello {user_name}! " if user_name else ""
    dest_title = destination.strip().title() if destination else "your destination"
    m_lower = message.lower()
    
    # Route: Delhi to Manali
    if 'delhi' in m_lower and 'manali' in m_lower:
        return (
            f"{prefix}Here is the best way to travel from **Delhi to Manali**:\n\n"
            f"### 🚌 1. Overnight Volvo / Scania Bus (Most Popular & Comfortable)\n"
            f"* **Boarding Points**: Kashmere Gate ISBT or Majnu Ka Tilla in Delhi.\n"
            f"* **Operators**: HRTC Himgaurav / HPTDC Luxury or reputable private Volvos.\n"
            f"* **Duration**: 10 to 12 hours (new Kiratpur-Manali highway and tunnels have cut travel time significantly).\n"
            f"* **Cost**: ₹1,200 – ₹1,900 per semi-sleeper berth.\n\n"
            f"### ✈️ 2. By Air (Fastest)\n"
            f"* Fly from Delhi (DEL) to Kullu-Manali Airport at Bhuntar (KUU), then take a 1.5-hour taxi to Manali (~₹1,800–₹2,500 cab fare).\n\n"
            f"### 🚗 3. Self-Drive / Private Taxi\n"
            f"* Route via NH44 through Panipat, Kurukshetra, Kiratpur Sahib, Bilaspur, Sundernagar, and Mandi.\n\n"
            f"> 💡 *Tip: Book your return Volvo ticket in advance during peak summer (May–June) and snowfall months (Dec–Jan)!*"
        )
        
    return (
        f"{prefix}Here is your complete transit and commute guide for **{dest_title}**:\n\n"
        f"### 🚆 How to Reach {dest_title}\n"
        f"* **By Train**: Book through IRCTC well in advance. Check for express or Vande Bharat connections to the nearest railway junction.\n"
        f"* **By Air**: Identify the nearest domestic/international airport; airport taxi booths provide transparent prepaid rates.\n"
        f"* **By Bus**: State-run luxury buses (HRTC, KSRTC, RSRTC, UPSRTC) offer reliable overnight services between major transit hubs.\n\n"
        f"### 🛵 Getting Around Locally\n"
        f"* **Scooter / Bike Rentals**: The ideal way to explore at your own pace (typically ₹350 – ₹600/day for gearless scooters; ₹900 – ₹1,500 for Royal Enfield). Always wear helmets and carry a valid driving license.\n"
        f"* **Auto-Rickshaws & Cabs**: Confirm meter or agree on fare before boarding. In major cities, app-based cabs (Ola, Uber, Rapido) offer fixed upfront pricing.\n"
        f"* **Shared Jeeps & Local Ferries**: For scenic routes or backwaters, local ferries and shared jeeps provide scenic transit at fraction of private costs.\n\n"
        f"> 💡 *Need specific directions from your hometown or flight recommendations? Just ask!*"
    )


def _generate_safety_reply(destination, message, user_name=None):
    """Provides empowering and practical travel safety advice."""
    prefix = f"Hello {user_name}! " if user_name else ""
    dest_title = destination.strip().title() if destination else "popular travel destinations in India"
    
    return (
        f"{prefix}Here is your dedicated travel safety guide for **{dest_title}**:\n\n"
        f"### 🛡️ Safety Assessment & Peace of Mind\n"
        f"* **Welcoming Atmosphere**: Most leisure destinations (especially Himachal Pradesh, Kerala, Ladakh, Rajasthan, and Sikkim) have a strong tourism hospitality culture and friendly community support.\n"
        f"* **Solo & Women Travelers**: Thousands of solo travelers visit every month. Choosing well-rated social hostels (Zostel, goSTOPS, Hosteller) offers a great built-in community of verified fellow travelers.\n\n"
        f"### 🔑 Essential Safety Guidelines\n"
        f"* **Daylight Arrivals**: Schedule flights, trains, or buses to arrive during daytime hours so check-in is stress-free.\n"
        f"* **Live Location & Offline Maps**: Download offline Google Maps for remote valleys, and keep your family/friends updated on your route.\n"
        f"* **Avoid Common Tourist Scams**: Only hire registered guides with official ID cards; purchase monument tickets directly on official government portals (ASI); avoid unsolicited gemstone/perfume deals.\n\n"
        f"### 🚨 Emergency Contact Helplines (India)\n"
        f"* **National Emergency Number**: 112 (Police, Ambulance, Fire)\n"
        f"* **Women Helpline**: 1091\n"
        f"* **Tourist Helpline**: 1363 (24x7 multi-lingual toll-free)\n\n"
        f"> 💡 *Feel free to ask about safe neighborhoods, trusted transport operators, or female-friendly hostels!*"
    )


def _generate_budget_reply(destination, message, user_name=None):
    """Provides practical budget planning, cost breakdowns, and saving hacks."""
    prefix = f"Hello {user_name}! " if user_name else ""
    dest_title = destination.strip().title() if destination else "your trip"
    
    return (
        f"{prefix}Here is your complete budget breakdown and money-saving guide for **{dest_title}**:\n\n"
        f"### 💰 Three Budget Tiers Explained\n"
        f"* **Budget (Under ₹15,000 total trip)**:\n"
        f"  - Stay: Social hostel dorms or family guest houses (₹500 – ₹1,200/night)\n"
        f"  - Food: Iconic local dhabas, street food, and traditional thalis (₹200 – ₹400/day)\n"
        f"  - Transit: Sleeper / 3AC trains and state road transport buses\n\n"
        f"* **Moderate (₹15,000 – ₹50,000 total trip)**:\n"
        f"  - Stay: 3-star boutique hotels, heritage homestays, or hillside cottages (₹3,000 – ₹6,500/night)\n"
        f"  - Food: Popular cafes, multicuisine dining, and rooftop bistros (₹700 – ₹1,400/day)\n"
        f"  - Transit: 2AC train berths, domestic flights, or self-drive rentals\n\n"
        f"* **Luxury (Above ₹50,000 total trip)**:\n"
        f"  - Stay: 5-star palace hotels, luxury private villas, or wellness spa resorts (₹15,000 – ₹38,000/night)\n"
        f"  - Food: Fine dining gourmet experiences and private chef tables\n"
        f"  - Transit: Dedicated chauffeur-driven SUVs or premium business flights\n\n"
        f"### 💡 Top 4 Money-Saving Hacks\n"
        f"1. **Use UPI Everywhere**: GPay, PhonePe, and Paytm are accepted by virtually every tea stall and auto driver, saving ATM withdrawal surcharges.\n"
        f"2. **Book Trains 60–90 Days Early**: IRCTC advance booking guarantees confirmed lower-berth seats at base fares.\n"
        f"3. **Travel in Shoulder Season**: Traveling just before or after peak season gets you 30%–50% hotel discounts with fewer crowds.\n"
        f"4. **Rent a Scooter**: At ₹400/day, scooter rentals save thousands compared to point-to-point private taxis.\n\n"
        f"> 💡 *Tell me your target travel budget and group size, and I'll calculate your exact daily itinerary cost!*"
    )


def _generate_packing_reply(destination, message, user_name=None):
    """Provides tailored packing checklists based on destination climate and season."""
    prefix = f"Hello {user_name}! " if user_name else ""
    m_lower = message.lower()
    is_winter_mountain = any(k in m_lower for k in ['winter', 'snow', 'cold', 'mountain', 'kashmir', 'ladakh', 'manali', 'spiti', 'shimla'])
    is_beach = any(k in m_lower for k in ['beach', 'sea', 'coastal', 'goa', 'andaman', 'kerala', 'pondicherry', 'gokarna'])
    
    if is_winter_mountain:
        return (
            f"{prefix}Here is your **Winter / Mountain High-Altitude Packing Checklist**:\n\n"
            f"### 🧥 Clothing & The 3-Layer System\n"
            f"* **Base Layer**: 2–3 pairs of thermal innerwear (merino wool or quick-dry synthetic).\n"
            f"* **Mid Layer**: Fleece jackets, warm wool sweaters, and flannel shirts.\n"
            f"* **Outer Layer**: Windproof and water-resistant down jacket or heavy parka.\n"
            f"* **Bottoms**: Fleece-lined thermal pants / heavy trekking trousers.\n\n"
            f"### 🧤 Essential Accessories\n"
            f"* Waterproof snow gloves with thermal lining\n"
            f"* Fleece-lined beanie/cap covering ears and thermal neck gaiter\n"
            f"* 4–5 pairs of woolen socks & sturdy waterproof hiking boots with deep tread grip\n"
            f"* UV400 polarized sunglasses (essential to prevent snow blindness)\n\n"
            f"### 🧴 Skincare & Medical\n"
            f"* High-SPF sunscreen (SPF 50+) & hydrating lip balm (cold wind dries lips fast)\n"
            f"* Heavy moisturizing cream, cold relief meds, and portable hand warmers\n"
            f"* Insulated thermos flask for sipping hot water on trails\n\n"
            f"> 💡 *Tip: High altitude drains phone batteries fast—keep your power bank inside an inner jacket pocket!*"
        )
    elif is_beach:
        return (
            f"{prefix}Here is your **Beach & Coastal Vacation Packing Checklist**:\n\n"
            f"### 🏖️ Clothing & Footwear\n"
            f"* Breathable linen shirts, lightweight cotton tees, and shorts\n"
            f"* Swimwear, sarongs, and quick-dry rash guards for water sports\n"
            f"* Comfortable flip-flops for sand & breathable walking sneakers for exploring\n\n"
            f"### ☀️ Sun & Skin Protection\n"
            f"* Broad-spectrum, water-resistant sunscreen (SPF 50+)\n"
            f"* UV-polarized sunglasses and wide-brimmed sun hat\n"
            f"* Soothing aloe vera gel for post-sun care\n\n"
            f"### 🎒 Accessories & Gear\n"
            f"* Waterproof dry bag or phone pouch for boat rides & jet skiing\n"
            f"* Microfiber quick-dry beach towel\n"
            f"* Insect repellent spray for evening beach shacks\n\n"
            f"> 💡 *Tip: Remember to carry light cotton layers for visiting historic forts or air-conditioned cafes!*"
        )
    else:
        return (
            f"{prefix}Here is your **Smart Travel Packing Checklist** for any trip:\n\n"
            f"### 📄 Essential Documents\n"
            f"* Government photo ID (Aadhaar / Passport / Voter ID) + digital copies stored offline\n"
            f"* Hotel booking confirmations and flight/train e-tickets\n\n"
            f"### 🔌 Electronics & Gadgets\n"
            f"* Universal travel adapter & 20,000 mAh fast-charging power bank\n"
            f"* Braided charging cables, earphones, and lightweight camera/e-reader\n\n"
            f"### 💊 Health & Hygiene\n"
            f"* Personal prescription medications + motion sickness & pain relief tablets\n"
            f"* Hand sanitizer, electrolyte hydration packets (ORS), and adhesive bandages\n\n"
            f"> 💡 *Packing for a specific terrain like trekking, desert safari, or monsoon? Tell me where and when!*"
        )


def _generate_weather_reply(destination, message, user_name=None):
    """Provides seasonal insights, climate guidance, and best times to visit."""
    prefix = f"Hello {user_name}! " if user_name else ""
    dest_title = destination.strip().title() if destination else "popular destinations"
    
    return (
        f"{prefix}Here is the seasonal breakdown and best time to plan your visit to **{dest_title}**:\n\n"
        f"### 🗓️ Season-by-Season Guide\n"
        f"* **☀️ Peak Season (October to March)**:\n"
        f"  - Ideal climate across plains, deserts, and coastal India (20°C – 28°C).\n"
        f"  - Vibrant festive atmosphere, cultural fairs (Pushkar, Goa festivals, beach parties).\n"
        f"  - Best for sightseeing, outdoor treks, and heritage photography.\n\n"
        f"* **🌸 Summer / Spring (April to June)**:\n"
        f"  - Best time to head up into the Himalayas (Manali, Shimla, Leh-Ladakh, Spiti, Kashmir) to escape the heat.\n"
        f"  - Pleasant mountain weather, blossoming apple orchards, and open high-altitude passes.\n\n"
        f"* **🌧️ Monsoon / Off-Season (July to September)**:\n"
        f"  - Dramatic lush landscapes in Western Ghats, Kerala backwaters, and Udaipur lakes.\n"
        f"  - Huge hotel discounts (up to 40%–50% off standard rates) and peaceful tourist-free sightseeing.\n"
        f"  - Avoid high-risk landslide zones in steep mountain routes during heavy monsoon spells.\n\n"
        f"> 💡 *You can also click the **Weather** tab in the top navigation bar for live real-time forecasts!*"
    )


def _generate_offbeat_reply(destination, message, user_name=None):
    """Recommends hidden gems and peaceful offbeat escapes."""
    prefix = f"Hello {user_name}! " if user_name else ""
    
    return (
        f"{prefix}Here are breathtaking, peaceful **hidden gems & offbeat escapes** in India:\n\n"
        f"### 🏔️ 1. Jibhi & Tirthan Valley (Himachal Pradesh)\n"
        f"* Cozy wooden cottages, crystal-clear trout streams, Great Himalayan National Park trails, and peaceful pine woods away from crowded Manali.\n\n"
        f"### 🏜️ 2. Gandikota (Andhra Pradesh)\n"
        f"* Known as the *Grand Canyon of India*, featuring a dramatic gorge carved by the Penna river alongside a medieval 13th-century stone fort.\n\n"
        f"### 🌊 3. Dhanushkodi (Tamil Nadu)\n"
        f"* A hauntingly beautiful ghost hamlet at the tip of Pamban Island where the Bay of Bengal meets the Indian Ocean with pristine white sands.\n\n"
        f"### 🍃 4. Mechuka (Arunachal Pradesh)\n"
        f"* A magical high-altitude valley surrounded by snow-dusted peaks, wooden bridges, wild horses, and historic 400-year-old Buddhist monasteries.\n\n"
        f"### 🏝️ 5. Varkala & Marari (Kerala)\n"
        f"* Dramatic red laterite cliffs overlooking the Arabian Sea in Varkala, and peaceful fishermen hamlets in Marari—far quieter than standard beach strips.\n\n"
        f"> 💡 *Looking for an offbeat escape near a specific city like Delhi, Mumbai, or Bangalore? Let me know!*"
    )


def _generate_culture_reply(destination, message, user_name=None):
    """Provides cultural etiquette, temple guidelines, and local customs."""
    prefix = f"Hello {user_name}! " if user_name else ""
    
    return (
        f"{prefix}Here are thoughtful **cultural etiquette and temple guidelines** to ensure a respectful journey:\n\n"
        f"### 🛕 Temple & Religious Site Etiquette\n"
        f"* **Dress Modestly**: Cover shoulders and knees when visiting temples, mosques, gurdwaras, and churches. Loose cotton kurtas, pants, or scarves work best.\n"
        f"* **Footwear & Leather**: Remove your shoes outside shrines. Certain traditional temples (e.g. in South India or Rajasthan) also request depositing leather belts and wallets outside.\n"
        f"* **Head Coverings**: Cover your head with a scarf or rumal inside Sikh Gurdwaras (headscarves are provided free at the entrance).\n"
        f"* **Circumambulation (Pradakshina)**: Walk in a clockwise direction around shrines and stupas.\n\n"
        f"### 🤝 Social Customs & Tipping Norms\n"
        f"* **Greeting**: A warm *Namaste* with palms pressed together is respected and appreciated everywhere.\n"
        f"* **Eating & Giving**: Use your right hand when accepting prasad, food, or paying cash.\n"
        f"* **Tipping**: 5% – 10% is customary at sit-down restaurants if a service charge is not included; ₹50 – ₹100 for hotel bellhops is appreciated.\n\n"
        f"> 💡 *Ask me about specific customs for any state or heritage monument you are planning to visit!*"
    )


def _generate_adventure_reply(destination, message, user_name=None):
    """Details adventure sports, trekking routes, and outdoor activities."""
    prefix = f"Hello {user_name}! " if user_name else ""
    dest_title = destination.strip().title() if destination else "India"
    
    return (
        f"{prefix}Here are premier **adventure sports & outdoor activities** across {dest_title}:\n\n"
        f"### 🌊 1. White Water River Rafting (Rishikesh, Uttarakhand)\n"
        f"* Rapids from Grade II to Grade IV+ along the sacred Ganga (Marine Drive to Rishikesh, 26 km; or Shivpuri, 16 km).\n"
        f"* Estimated Cost: ₹800 – ₹1,600 per person with safety equipment and life jackets.\n\n"
        f"### 🪂 2. World-Class Paragliding (Bir Billing, Himachal Pradesh)\n"
        f"* World Paragliding Cup site at 2,400m offering 20–30 minute tandem flights with breathtaking views of the Dhauladhar range.\n"
        f"* Estimated Cost: ₹2,500 – ₹3,500 including GoPro action camera footage.\n\n"
        f"### 🤿 3. Scuba Diving & Snorkeling (Havelock Island, Andaman & Nicobar)\n"
        f"* Crystal-clear waters with rich coral reefs, sea turtles, and vibrant marine life at Elephant Beach and Nemo Reef.\n"
        f"* Estimated Cost: ₹3,500 – ₹5,500 for beginner PADI-certified discovery dives.\n\n"
        f"### 🥾 4. Scenic Beginner Treks\n"
        f"* **Triund Trek** (Dharamshala): 9 km scenic trail with night camping under the stars facing the Dhauladhar snowline.\n"
        f"* **Kedarkantha Trek** (Uttarakhand): Premier winter snow summit trek with 360-degree Himalayan vistas.\n\n"
        f"> 💡 *Which adventure calls out to you? I can help you with fitness prep, best months, and safety checklists!*"
    )


def _generate_visa_reply(destination, message, user_name=None):
    """Provides essential permit, visa, and document guidance."""
    prefix = f"Hello {user_name}! " if user_name else ""
    
    return (
        f"{prefix}Here is your **travel permits, visa & documentation guide**:\n\n"
        f"### 🇮🇳 Domestic Travel Permits (Inner Line Permits - ILP)\n"
        f"* **Required States for Indian Travelers**: Arunachal Pradesh, Nagaland, Mizoram, and Manipur.\n"
        f"* **Protected Areas**: Certain border zones in Ladakh (Pangong Tso, Nubra Valley, Khardung La) and Sikkim (Nathu La Pass, Tsomgo Lake) require permits.\n"
        f"* **How to Apply**: Most permits can now be applied for online via respective state government portals or arranged via registered local taxi/tour operators.\n\n"
        f"### ✈️ International Travel for Indian Passport Holders\n"
        f"* **Visa-Free / Easy Visa on Arrival (VoA)**: Thailand (visa-free tourism), Malaysia, Sri Lanka, Indonesia (Bali VoA), Maldives (30-day visa-free on arrival).\n"
        f"* **Essential Requirement**: Passport must have at least 6 months validity from departure date, return flight tickets, and confirmed hotel vouchers.\n\n"
        f"> 💡 *Have a specific international or domestic route in mind? Let me know and I will verify the exact requirements!*"
    )


def _generate_accommodation_reply(destination, message, user_name=None):
    """Guides travelers on where to stay and hotel options."""
    prefix = f"Hello {user_name}! " if user_name else ""
    dest_title = destination.strip().title() if destination else "your destination"
    
    return (
        f"{prefix}Here are top stay recommendations and neighborhood tips for **{dest_title}**:\n\n"
        f"### 🏨 Selecting the Right Neighborhood\n"
        f"* **Central / Walkable**: Ideal for short trips where you want quick access to landmark monuments, dining, and transit.\n"
        f"* **Tranquil Outskirts / Hillside**: Best for relaxation, scenic sunset vistas, private nature retreats, and slower travel.\n\n"
        f"### 💰 Three Stay Categories\n"
        f"* **Budget (Under ₹15,000 trip)**: Verified backpacker hostels (Zostel, goSTOPS) or family-run homestays (₹600 – ₹1,500/night).\n"
        f"* **Moderate (₹15,000 – ₹50,000 trip)**: Boutique heritage havelis, comfort suites, or riverside resorts (₹3,500 – ₹7,000/night).\n"
        f"* **Luxury (Above ₹50,000 trip)**: Historic royal palaces, 5-star seaside villas, or premier wellness retreats (₹16,000 – ₹40,000/night).\n\n"
        f"> 💡 *Check out the **Hotels** tab in the navigation bar to see live hotel listings, verified ratings, and direct website links!*"
    )


def _generate_destination_overview(destination, user_name=None):
    """Provides a personalized introduction to a specific destination."""
    prefix = f"Hello {user_name}! " if user_name else ""
    rec = _lookup_destination_record(destination)
    dest_title = destination.strip().title()
    
    if rec:
        return (
            f"{prefix}Here is what makes **{rec['name']}** in {rec['state']} special:\n\n"
            f"### 🌟 Overview & Atmosphere\n"
            f"{rec['description']}\n\n"
            f"### 📌 Quick Travel Facts\n"
            f"* **Primary Category**: {rec['category']}\n"
            f"* **Typical Budget Level**: {rec['budget_level']}\n"
            f"* **Highlights & Tags**: #{' #'.join(str(rec.get('tags', '')).split())}\n\n"
            f"### 🧭 What Would You Like to Know Next?\n"
            f"* 📅 Plan a custom day-by-day itinerary\n"
            f"* 🍲 Signature local foods and dining recommendations\n"
            f"* 🚆 Best way to reach and local commute options\n"
            f"* ☀️ Best season to visit and weather updates\n\n"
            f"> 💡 *Ask me any question above to dive deeper into {rec['name']}!*"
        )

    return (
        f"{prefix}**{dest_title}** is an exciting place to explore!\n\n"
        f"I can help you plan everything for your journey to {dest_title}:\n"
        f"* 📅 Day-by-day custom itineraries for any duration\n"
        f"* 🍛 Must-try regional food and cafe spots\n"
        f"* 🏨 Hotels sorted accurately by your budget tier\n"
        f"* 🎒 Packing advice and live weather forecasts\n\n"
        f"> 💡 *How many days are you planning for your visit to {dest_title}, or what specific question do you have?*"
    )


def _generate_welcome_reply(user_name=None):
    """Friendly personalized welcome overview of TravelAI capabilities."""
    name_str = f", {user_name}" if user_name else ""
    return (
        f"### 👋 Hello{name_str}! Welcome to TravelAI Companion!\n\n"
        f"I'm your 24/7 personal travel assistant and expert concierge. Here are just a few things we can do together:\n\n"
        f"* 🏝️ **Explore Destinations**: Recommendations matching your budget, season, or travel style.\n"
        f"* 📅 **Day-by-Day Itineraries**: Custom plans covering the exact number of days you want.\n"
        f"* 🍲 **Culinary & Foodie Tips**: Signature local dishes, street food hubs, and must-visit cafes.\n"
        f"* 🚆 **Transport & Commute**: Routes, Volvo buses, Vande Bharat trains, scooter rentals, and cab tips.\n"
        f"* 💰 **Budget Hacks & Costs**: Realistic estimates in ₹ across Budget, Moderate, and Luxury tiers.\n"
        f"* 🛡️ **Safety & Solo Travel**: Neighborhood guidance, tips for female travelers, and emergency helplines.\n"
        f"* 🎒 **Smart Packing Checklists**: Tailored for winter snow, beach vacations, or monsoon trails.\n\n"
        f"> 💡 *Where are you thinking of traveling, or what travel question is on your mind today?*"
    )


def _has_intent(keywords, text):
    """Checks if any keyword matches as a full word or phrase boundary in text."""
    for kw in keywords:
        pattern = r'\b' + re.escape(kw) + r'\b'
        if re.search(pattern, text, re.I):
            return True
    return False


def _generate_fallback_travel_reply(message, user_name=None, context=None):
    """
    Intelligently classifies user query intent and provides personalized, rich responses
    across all travel topics in offline fallback mode or when Gemini API is unconfigured.
    """
    m = message.lower().strip()
    destination = _extract_destination(message, context=context)

    # 1. Day-by-Day Itinerary Request
    if _is_itinerary_request(message):
        num_days = _extract_requested_days(message)
        dest = destination or "Your Destination"
        return _generate_fallback_itinerary(num_days, dest, user_name=user_name)

    # 2. Offbeat & Hidden Gems (Check before general destination overview)
    if _has_intent(['offbeat', 'hidden gems', 'hidden places', 'hidden spot', 'hidden spots', 'unexplored', 'secret places', 'quiet places', 'peaceful getaway', 'less crowded', 'crowd free', 'alternatives'], m):
        return _generate_offbeat_reply(destination, message, user_name=user_name)

    # 3. Food, Dining & Culinary Specialties
    if _has_intent(['food', 'foods', 'street food', 'street foods', 'dish', 'dishes', 'eat', 'eating', 'cuisine', 'cuisines', 'restaurant', 'restaurants', 'cafe', 'cafes', 'dining', 'culinary', 'breakfast', 'lunch', 'dinner', 'delicacies', 'delicacy', 'snacks', 'snack', 'veg', 'vegan', 'thali', 'thalis', 'sweets', 'sweet', 'eateries', 'eatery'], m):
        return _generate_food_reply(destination, message, user_name=user_name)

    # 4. Transportation, How to Reach & Commute
    if _has_intent(['transport', 'transportation', 'how to reach', 'how to get', 'how to travel', 'how to go', 'travel from', 'travel to', 'travel between', 'route', 'distance', 'train', 'trains', 'bus', 'buses', 'flight', 'flights', 'cab', 'cabs', 'taxi', 'taxis', 'scooter', 'bike', 'commute', 'metro', 'vande bharat', 'auto rickshaw', 'airport', 'railway', 'drive', 'driving', 'ferry'], m):
        return _generate_transport_reply(destination, message, user_name=user_name)

    # 5. Safety & Solo Travel
    if _has_intent(['safe', 'safety', 'solo', 'female', 'woman', 'women', 'emergency', 'scam', 'scams', 'precautions', 'night', 'alone', 'helpline'], m):
        return _generate_safety_reply(destination, message, user_name=user_name)

    # 6. Budget, Costs & Money Saving Hacks
    if _has_intent(['budget', 'cost', 'costs', 'expense', 'expenses', 'cheap', 'save money', 'hacks', 'how much', 'prices', 'rates', 'affordable', 'under 15000', 'backpacking', 'money', 'fare'], m):
        return _generate_budget_reply(destination, message, user_name=user_name)

    # 7. Culture, Etiquette & Sacred Sites (Prioritized for temple & cultural inquiries)
    if _has_intent(['culture', 'etiquette', 'temple', 'temples', 'mosque', 'gurdwara', 'customs', 'custom', 'tipping', 'tradition', 'traditions', 'local norms', 'religious'], m):
        return _generate_culture_reply(destination, message, user_name=user_name)

    # 8. Packing & Gear Checklist
    if _has_intent(['pack', 'packing', 'what to pack', 'carry', 'clothes', 'clothing', 'luggage', 'gear', 'shoes', 'dress code', 'winter clothes', 'what to wear', 'jacket', 'boots'], m):
        return _generate_packing_reply(destination, message, user_name=user_name)

    # 9. Best Time to Visit, Seasons & Climate
    if _has_intent(['weather', 'best time', 'season', 'seasons', 'when to visit', 'climate', 'temperature', 'temperatures', 'rain', 'snow', 'monsoon', 'summer', 'winter', 'best season', 'forecast'], m):
        return _generate_weather_reply(destination, message, user_name=user_name)

    # 10. Adventure & Outdoor Sports
    if _has_intent(['adventure', 'trek', 'trekking', 'hiking', 'hike', 'rafting', 'paragliding', 'scuba', 'bungee', 'safari', 'water sports', 'camping', 'kayaking', 'zipline'], m):
        return _generate_adventure_reply(destination, message, user_name=user_name)

    # 11. Visas, Permits & Documentation
    if _has_intent(['visa', 'visas', 'permit', 'permits', 'ilp', 'inner line', 'passport', 'passports', 'documents', 'id proof'], m):
        return _generate_visa_reply(destination, message, user_name=user_name)

    # 12. Accommodations & Stays
    if _has_intent(['hotel', 'hotels', 'stay', 'stays', 'resort', 'resorts', 'hostel', 'hostels', 'homestay', 'where to stay', 'villa', 'zostel', 'accommodations', 'lodging'], m):
        return _generate_accommodation_reply(destination, message, user_name=user_name)

    # 13. Specific Destination Overview
    if destination:
        return _generate_destination_overview(destination, user_name=user_name)

    # 14. Fallback Welcome / General Guidance
    return _generate_welcome_reply(user_name=user_name)


def ask_travel_gemini(message, history=None, user_name=None, context=None):
    """
    Main entry point for travel questions.
    Personalized for traveler name and context.
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
        logger.info("GEMINI_API_KEY not configured. Using TravelAI assistant personalized offline fallback mode.")
        return _generate_fallback_travel_reply(message, user_name=user_name, context=context)

    clean_msg = message.strip()

    # If user explicitly requests an itinerary, reinforce the requested days in the prompt
    if _is_itinerary_request(clean_msg):
        num_days = _extract_requested_days(clean_msg)
        reinforced_msg = f"{clean_msg}\n\n[Please generate a complete day-by-day plan covering all {num_days} days from Day 1 to Day {num_days}.]"
    else:
        reinforced_msg = clean_msg

    # 1. Try official google-genai SDK
    try:
        reply = _ask_via_google_genai_sdk(api_key, model_name, reinforced_msg, history=history, user_name=user_name, context=context)
        if reply:
            return reply
    except Exception as e:
        logger.warning(f"google-genai SDK invocation encountered issue: {e}. Trying REST fallback...")

    # 2. Try direct REST API fallback
    try:
        reply = _ask_via_rest_api(api_key, model_name, reinforced_msg, history=history, user_name=user_name, context=context)
        if reply:
            return reply
    except Exception as e:
        logger.error(f"Gemini REST invocation failed: {e}")

    # 3. Fallback to dynamic travel reply generator
    return _generate_fallback_travel_reply(message, user_name=user_name, context=context)
