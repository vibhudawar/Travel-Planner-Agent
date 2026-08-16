"""Deterministic budget, date, and currency computation (plan-v2.md WIN 4).

Anything checkable is computed in code from the WIN 3 structured facts — never by
the LLM, which does arithmetic unreliably (the WIN 3 baseline showed budgets with
no total, and one that echoed the user's *budget cap* as the total). The
synthesize node overwrites the model-proposed budget with ``compute_budget()``'s
result, so a shipped itinerary's budget always adds up and is derived from real
prices and real dates.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional, TypedDict

# Static FX rates to USD. Tools return USD today; extend this as other currencies
# appear (WIN 5). An amount in an unknown currency is surfaced, never guessed.
_RATES_TO_USD = {"USD": 1.0}


def parse_date(value) -> Optional[date]:
    """Parse an ISO-ish date string (YYYY-MM-DD...) into a date, else None."""
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


def trip_nights(start, end) -> Optional[int]:
    """Number of hotel nights between two dates, or None if not derivable."""
    s, e = parse_date(start), parse_date(end)
    if not s or not e:
        return None
    nights = (e - s).days
    return nights if nights > 0 else None


def to_usd(amount: float, currency: Optional[str]) -> Optional[float]:
    """Convert to USD via the static rate table; None if the currency is unknown."""
    rate = _RATES_TO_USD.get((currency or "USD").upper())
    return None if rate is None else amount * rate


class ComputedBudget(TypedDict):
    currency: str
    items: List[dict]
    total: float
    nights: Optional[int]
    travelers: int
    mixed_currency: bool


def compute_budget(itinerary: dict, travelers: Optional[int] = None) -> ComputedBudget:
    """Compute an authoritative budget from the itinerary's source-bound facts.

    - flights: cheapest option's price x travelers
    - hotel: cheapest option's nightly price x nights (from the dates)
    Amounts are normalized to USD; a fact in an unknown currency sets
    ``mixed_currency`` rather than being silently included at face value.
    Attractions carry no price data in the tools, so they are not costed.
    """
    n_travelers = travelers or itinerary.get("travelers") or 1
    nights = trip_nights(itinerary.get("start_date"), itinerary.get("end_date"))
    items: List[dict] = []
    mixed_currency = False

    flights = [f for f in itinerary.get("flights", []) if f.get("price") is not None]
    if flights:
        cheapest = min(flights, key=lambda f: f["price"])
        usd = to_usd(cheapest["price"], cheapest.get("currency", "USD"))
        if usd is None:
            mixed_currency = True
        else:
            items.append(
                {
                    "label": f"Flights ({cheapest.get('airline', '?')}, x{n_travelers} traveler(s))",
                    "amount": round(usd * n_travelers, 2),
                    "source_tool": "search_flights",
                }
            )

    hotels = [h for h in itinerary.get("hotels", []) if h.get("price_per_night") is not None]
    if hotels and nights:
        cheapest = min(hotels, key=lambda h: h["price_per_night"])
        usd = to_usd(cheapest["price_per_night"], cheapest.get("currency", "USD"))
        if usd is None:
            mixed_currency = True
        else:
            items.append(
                {
                    "label": f"Hotel ({cheapest.get('name', '?')}, x{nights} night(s))",
                    "amount": round(usd * nights, 2),
                    "source_tool": "search_hotels",
                }
            )

    total = round(sum(i["amount"] for i in items), 2)
    return {
        "currency": "USD",
        "items": items,
        "total": total,
        "nights": nights,
        "travelers": n_travelers,
        "mixed_currency": mixed_currency,
    }
