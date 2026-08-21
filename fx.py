"""Live foreign-exchange rates (USD → currency), cached 24h, with a static fallback.

Tools price everything in USD; the itinerary shows the total in the user's home
currency (e.g. INR). A stale FX rate is fine for a day, so we hit a free, keyless
endpoint once and cache the result for 24h. If the network/endpoint is unavailable
we fall back to an approximate static rate (clearly flagged) rather than failing.
"""
from __future__ import annotations

import logging
from typing import Tuple

import requests

from tools import get_cache

logger = logging.getLogger(__name__)

# Approximate units-of-currency per 1 USD, used only when the live rate is
# unavailable. Deliberately rough — the note in the UI flags it as approximate.
_FALLBACK_PER_USD = {
    "USD": 1.0, "INR": 86.0, "EUR": 0.92, "GBP": 0.79, "AED": 3.67,
    "JPY": 155.0, "SGD": 1.35, "THB": 36.0, "AUD": 1.52, "CAD": 1.37,
}

_CACHE_TTL_SECONDS = 24 * 3600
_ENDPOINT = "https://open.er-api.com/v6/latest/USD"


def usd_to(currency: str) -> Tuple[float, bool]:
    """Return (units_of_currency_per_1_USD, is_live). 24h-cached; static fallback."""
    code = (currency or "USD").upper()
    if code == "USD":
        return (1.0, True)

    cache = get_cache()
    cache_key = f"fx:USD:{code}"
    cached = cache.get(cache_key)
    if cached is not None:
        return (float(cached), True)

    try:
        resp = requests.get(_ENDPOINT, timeout=10)
        resp.raise_for_status()
        rate = (resp.json().get("rates") or {}).get(code)
        if rate:
            cache.set(cache_key, float(rate), expire=_CACHE_TTL_SECONDS)
            logger.info("FX USD->%s = %s (live, cached 24h)", code, rate)
            return (float(rate), True)
        logger.warning("FX endpoint had no rate for %s; using fallback", code)
    except Exception as exc:  # noqa: BLE001 - never fail the itinerary on FX
        logger.warning("FX fetch failed (%s); using fallback", exc)

    fallback = _FALLBACK_PER_USD.get(code)
    return (fallback, False) if fallback else (0.0, False)
