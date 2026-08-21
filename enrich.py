"""Attach actionable links to verified itinerary facts (code-authored).

Links come from the real tool results (hotels, attractions) or are constructed as
Google Maps / Google Flights search URLs (flights, since SerpAPI returns only a
booking token). Matching is done in code — never by the LLM — so a URL can't be
truncated or hallucinated, and only facts that survived the verifier get a link.
"""
from __future__ import annotations

import ast
import json
from typing import Optional

from langchain_core.messages import ToolMessage

from tools import google_flights_link


def _parse(content) -> Optional[dict]:
    """Best-effort parse of a ToolMessage payload into a dict."""
    if isinstance(content, dict):
        return content
    for parser in (json.loads, ast.literal_eval):
        try:
            value = parser(content)
            return value if isinstance(value, dict) else None
        except Exception:  # noqa: BLE001 - tolerant parse
            continue
    return None


def _norm(value) -> str:
    """Alphanumeric-only lowercase key for tolerant name matching."""
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _collect(messages) -> dict:
    """Merge tool results by kind: hotels + attractions carry usable links."""
    hotels: list = []
    attractions: list = []
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        data = _parse(msg.content)
        if not data:
            continue
        if getattr(msg, "name", None) == "search_hotels":
            hotels.extend(data.get("hotels", []) or [])
        elif getattr(msg, "name", None) == "search_attractions":
            attractions.extend(data.get("attractions", []) or [])
    return {"hotels": hotels, "attractions": attractions}


def attach_links(itinerary: dict, messages) -> dict:
    """Populate link fields on the itinerary's facts, in place, and return it."""
    tool_data = _collect(messages)

    hotel_links = {_norm(h.get("name")): h.get("link") for h in tool_data["hotels"] if h.get("link")}
    for hotel in itinerary.get("hotels", []) or []:
        if not hotel.get("link"):
            link = hotel_links.get(_norm(hotel.get("name")))
            if link:
                hotel["link"] = link

    attr_links = {_norm(a.get("name")): a.get("link") for a in tool_data["attractions"] if a.get("link")}
    for attraction in itinerary.get("attractions", []) or []:
        if not attraction.get("link"):
            link = attr_links.get(_norm(attraction.get("name")))
            if link:
                attraction["link"] = link

    # Flights: no per-option URL from the API — attach a Google Flights route search.
    origin, dest, date = itinerary.get("origin"), itinerary.get("destination"), itinerary.get("start_date")
    if origin and dest:
        route_link = google_flights_link(origin, dest, date)
        for flight in itinerary.get("flights", []) or []:
            if not flight.get("booking_link"):
                flight["booking_link"] = route_link

    return itinerary
