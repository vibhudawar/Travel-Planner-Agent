"""
Trip Planner Tools
All tool functions with @tool decorator for dynamic LLM tool selection
"""
import os
import logging
from typing import Dict, Any, Optional
import requests
import diskcache
from serpapi import GoogleSearch
from langchain_core.tools import tool
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize cache
cache = diskcache.Cache(os.getenv("CACHE_DIR", "./cache"))

# ====================== Utility Tools ======================

@tool
def calculator(first_num: float, second_num: float, operation: str) -> dict:
    """
    Perform a basic arithmetic operation on two numbers.
    Supported operations: add, sub, mul, div
    """
    try:
        if operation == "add":
            result = first_num + second_num
        elif operation == "sub":
            result = first_num - second_num
        elif operation == "mul":
            result = first_num * second_num
        elif operation == "div":
            if second_num == 0:
                return {"error": "Division by zero is not allowed"}
            result = first_num / second_num
        else:
            return {"error": f"Unsupported operation '{operation}'"}
        
        return {"first_num": first_num, "second_num": second_num, "operation": operation, "result": result}
    except Exception as e:
        return {"error": str(e)}


@tool
def google_search(query: str) -> dict:
    """
    Search the web using Google AI Mode to get AI-curated search results and summaries.

    Args:
        query: Search query string

    Returns:
        Dictionary with AI-generated summary, quick results, references, and relevant content
    """
    params = {
        "engine": "google_ai_mode",
        "q": query,
        "hl": "en"
    }

    result = _serpapi_search(params, "google_search")

    if "error" in result:
        logger.error(f"Google search error: {result['error']}")
        return {"error": result["error"]}

    # Parse and structure the response
    response = {}

    # 1. Extract AI-generated text summary from text_blocks
    text_blocks = result.get("text_blocks", [])
    summary_parts = []

    for block in text_blocks:
        block_type = block.get("type")
        snippet = block.get("snippet", "")

        if block_type in ["heading", "paragraph"]:
            if snippet:
                summary_parts.append(snippet)
        elif block_type == "list":
            list_items = block.get("list", [])
            for item in list_items:
                item_snippet = item.get("snippet", "") or item.get("title", "")
                if item_snippet:
                    summary_parts.append(f"• {item_snippet}")

    response["summary"] = "\n\n".join(summary_parts) if summary_parts else "No summary available"
    return response


# ====================== Caching Utilities ======================

def get_cached(key: str) -> Optional[Any]:
    """Get cached value by key"""
    return cache.get(key)


def set_cached(key: str, value: Any, expiry_hours: int = 6) -> None:
    """Set cached value with expiry"""
    cache.set(key, value, expire=expiry_hours * 3600)


def _serpapi_search(params: Dict[str, Any], cache_key_prefix: str = "") -> Dict[str, Any]:
    """
    Execute SerpAPI search with caching

    Args:
        params: Search parameters
        cache_key_prefix: Prefix for cache key

    Returns:
        Search results dictionary
    """
    cache_key = f"{cache_key_prefix}:{str(params)}"

    # Check cache
    cached_result = get_cached(cache_key)
    if cached_result:
        logger.info(f"Cache hit for {cache_key_prefix}")
        return cached_result

    # Execute search
    try:
        api_key = os.getenv("SERPAPI_API_KEY")
        if not api_key:
            return {"error": "SERPAPI_API_KEY not found in environment"}

        params["api_key"] = api_key
        search = GoogleSearch(params)
        result = search.get_dict()

        # Cache result
        set_cached(cache_key, result)
        logger.info(f"SerpAPI search completed: {cache_key_prefix}")

        return result

    except Exception as e:
        logger.error(f"SerpAPI search failed: {cache_key_prefix} - {str(e)}")
        return {"error": str(e)}


# ====================== Travel Tools ======================

@tool
def search_flights(
    departure: str,
    arrival: str,
    outbound_date: str,
    return_date: Optional[str] = None,
    adults: int = 1
) -> dict:
    """
    Search for flight options between two cities using Google Flights via SerpAPI.

    Args:
        departure: Departure airport code or city name (e.g., "JFK" or "New York")
        arrival: Arrival airport code or city name (e.g., "CDG" or "Paris")
        outbound_date: Departure date in YYYY-MM-DD format
        return_date: Return date in YYYY-MM-DD format (optional, for round trip)
        adults: Number of adult passengers (default: 1)

    Returns:
        Dictionary with flight options including prices, airlines, and durations
    """
    params = {
        "engine": "google_flights",
        "departure_id": departure,
        "arrival_id": arrival,
        "outbound_date": outbound_date,
        "adults": adults,
        "currency": "USD",
        "hl": "en"
    }

    if return_date:
        params["return_date"] = return_date
        params["type"] = "1"  # Round trip
    else:
        params["type"] = "2"  # One way

    result = _serpapi_search(params, "flights")

    if "error" in result:
        logger.error(f"Flight search error: {result['error']}")
        return {"flights": [], "error": result["error"]}

    # Extract best flights
    best_flights = result.get("best_flights", [])
    other_flights = result.get("other_flights", [])
    all_flights = best_flights + other_flights

    # Format flight data
    flights = []
    for flight in all_flights[:10]:  # Top 10 flights
        flights.append({
            "price": flight.get("price"),
            "airline": ", ".join([leg.get("airline", "") for leg in flight.get("flights", [])]),
            "departure_time": flight.get("flights", [{}])[0].get("departure_airport", {}).get("time"),
            "arrival_time": flight.get("flights", [{}])[-1].get("arrival_airport", {}).get("time"),
            "duration": flight.get("total_duration"),
            "stops": len(flight.get("flights", [])) - 1,
            "booking_token": flight.get("booking_token")
        })

    logger.info(f"Found {len(flights)} flights from {departure} to {arrival}")
    return {"flights": flights, "count": len(flights)}


@tool
def search_hotels(
    location: str,
    check_in_date: str,
    check_out_date: str,
    adults: int = 2
) -> dict:
    """
    Search for hotel accommodations in a location using Google Hotels via SerpAPI.

    Args:
        location: City or location name (e.g., "Paris, France")
        check_in_date: Check-in date in YYYY-MM-DD format
        check_out_date: Check-out date in YYYY-MM-DD format
        adults: Number of adult guests (default: 2)

    Returns:
        Dictionary with hotel options including prices, ratings, and amenities
    """
    params = {
        "engine": "google_hotels",
        "q": location,
        "check_in_date": check_in_date,
        "check_out_date": check_out_date,
        "adults": adults,
        "currency": "USD",
        "gl": "us",
        "hl": "en",
        "sort_by": "3"  # Sort by lowest price
    }

    result = _serpapi_search(params, "hotels")

    if "error" in result:
        logger.error(f"Hotel search error: {result['error']}")
        return {"hotels": [], "error": result["error"]}

    # Extract properties
    properties = result.get("properties", [])

    # Sort by value (price + rating composite score)
    def calculate_value_score(hotel):
        price = hotel.get("rate_per_night", {}).get("extracted_lowest", 0)
        rating = hotel.get("overall_rating", 0)

        if not price or price == 0:
            return 0

        # Normalize (assuming max price ~500, max rating 5)
        norm_price = min(price / 500, 1.0)
        norm_rating = rating / 5.0 if rating else 0

        # 60% weight on price, 40% on rating
        return (1 - norm_price) * 0.6 + norm_rating * 0.4

    sorted_properties = sorted(properties, key=calculate_value_score, reverse=True)

    # Format hotel data
    hotels = []
    for prop in sorted_properties[:10]:  # Top 10 hotels
        hotels.append({
            "name": prop.get("name"),
            "price": prop.get("rate_per_night", {}).get("extracted_lowest"),
            "rating": prop.get("overall_rating"),
            "reviews": prop.get("reviews"),
            "amenities": prop.get("amenities", [])[:5],
            "link": prop.get("link"),
            "description": prop.get("description", "")[:200]
        })

    logger.info(f"Found {len(hotels)} hotels in {location}")
    return {"hotels": hotels, "count": len(hotels)}


@tool
def search_weather(location: str, start_date: str, end_date: str) -> dict:
    """
    Get weather forecast for a location and date range using OpenWeather Assistant API.

    Args:
        location: City or location name (e.g., "Paris, France")
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        Dictionary with human-readable weather forecast information
    """
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        return {"error": "OPENWEATHER_API_KEY not found in environment"}

    # Create natural language prompt
    prompt = f"What's the weather forecast for {location} from {start_date} to {end_date}?"

    # Check cache
    cache_key = f"weather_assistant:{prompt}"
    cached_result = get_cached(cache_key)
    if cached_result:
        logger.info("Weather cache hit")
        return {"weather": cached_result}

    try:
        url = "https://api.openweathermap.org/assistant/session"
        response = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": api_key
            },
            json={"prompt": prompt},
            timeout=30
        )
        response.raise_for_status()

        result = response.json()
        answer = result.get("answer")

        if answer:
            # Cache result
            set_cached(cache_key, answer)
            logger.info(f"Weather retrieved for {location}")
            return {"weather": answer}
        else:
            return {"error": "No weather data returned from API"}

    except Exception as e:
        logger.error(f"Weather API error: {str(e)}")
        return {"error": str(e)}


@tool
def search_attractions(location: str, category: str = "tourist_attraction") -> dict:
    """
    Find tourist attractions and places to visit using Google Maps via SerpAPI.

    Args:
        location: City or location name (e.g., "Paris, France")
        category: Type of attractions (default: "tourist_attraction")
                 Options: "tourist_attraction", "museum", "park", "restaurant"

    Returns:
        Dictionary with list of attractions including names, ratings, and descriptions
    """
    params = {
        "engine": "google_maps",
        "q": f"{category} in {location}",
        "type": "search",
        "hl": "en"
    }

    result = _serpapi_search(params, f"attractions_{location}")

    if "error" in result:
        logger.error(f"Attractions search error: {result['error']}")
        return {"attractions": [], "error": result["error"]}

    # Extract local results
    local_results = result.get("local_results", [])

    # Format attraction data
    attractions = []
    for place in local_results[:15]:  # Top 15 attractions
        attractions.append({
            "name": place.get("title"),
            "rating": place.get("rating"),
            "reviews": place.get("reviews"),
            "type": place.get("type"),
            "address": place.get("address"),
            "description": place.get("description", "")[:200]
        })

    logger.info(f"Found {len(attractions)} attractions in {location}")
    return {"attractions": attractions, "count": len(attractions)}


@tool
def search_youtube_vlogs(query: str, max_results: int = 5) -> dict:
    """
    Search for travel vlogs and guides on YouTube using SerpAPI.

    Args:
        query: Search query (e.g., "Paris travel guide 2025")
        max_results: Maximum number of results to return (default: 5)

    Returns:
        Dictionary with YouTube video information including titles, channels, and links
    """
    params = {
        "engine": "youtube",
        "search_query": query,
        "hl": "en"
    }

    result = _serpapi_search(params, f"youtube_{query}")

    if "error" in result:
        logger.error(f"YouTube search error: {result['error']}")
        return {"videos": [], "error": result["error"]}

    # Extract video results
    video_results = result.get("video_results", [])

    # Format video data
    videos = []
    for video in video_results[:max_results]:
        videos.append({
            "title": video.get("title"),
            "channel": video.get("channel", {}).get("name"),
            "views": video.get("views"),
            "published": video.get("published_date"),
            "duration": video.get("length"),
            "link": video.get("link"),
            "thumbnail": video.get("thumbnail", {}).get("static")
        })

    logger.info(f"Found {len(videos)} YouTube videos for '{query}'")
    return {"videos": videos, "count": len(videos)}


# Export all tools as a list
ALL_TOOLS = [
    search_flights,
    search_hotels,
    search_weather,
    search_attractions,
    search_youtube_vlogs,
    google_search,
    calculator
]
