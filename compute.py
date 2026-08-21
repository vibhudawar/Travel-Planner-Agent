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

# Static FX rates: value = USD per 1 unit of the currency (so INR 1 ≈ $0.0116).
# Tools price in USD; these let us (a) normalize a stray non-USD fact and (b) show
# the total in the user's home currency for legibility. Approximate and labelled
# as such — never presented as a live rate. Extend as needed.
_RATES_TO_USD = {
    "USD": 1.0,
    "INR": 1 / 86.0,
    "EUR": 1.08,
    "GBP": 1.27,
    "AED": 0.27,
    "JPY": 1 / 155.0,
    "SGD": 0.74,
    "THB": 1 / 36.0,
    "AUD": 0.66,
    "CAD": 0.73,
}

_CURRENCY_SYMBOL = {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£", "JPY": "¥"}


def normalize_currency(code: Optional[str]) -> Optional[str]:
    """Map common symbols/aliases to an ISO code we know, else the upper code."""
    if not code:
        return None
    c = str(code).strip().upper()
    aliases = {
        "₹": "INR", "RS": "INR", "RS.": "INR", "RUPEES": "INR", "RUPEE": "INR", "INR": "INR",
        "$": "USD", "US$": "USD", "USD": "USD", "DOLLAR": "USD", "DOLLARS": "USD",
        "€": "EUR", "£": "GBP", "¥": "JPY",
    }
    return aliases.get(c, c)


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
    # Home-currency display + budget adherence (all None when not applicable).
    cap: Optional[float]
    cap_currency: Optional[str]
    home_currency: Optional[str]
    total_home: Optional[float]
    cap_home: Optional[float]
    fx_rate: Optional[float]
    fx_note: Optional[str]
    over_budget: Optional[bool]
    over_by_home: Optional[float]
    assessment: Optional[str]


def _fmt_money(amount: float, currency: str) -> str:
    """Human-readable amount, e.g. '₹1,59,000' style falls back to grouped digits."""
    sym = _CURRENCY_SYMBOL.get(currency.upper(), currency.upper() + " ")
    return f"{sym}{amount:,.0f}"


def compute_budget(
    itinerary: dict,
    travelers: Optional[int] = None,
    budget_cap: Optional[float] = None,
    budget_currency: Optional[str] = None,
) -> ComputedBudget:
    """Compute an authoritative budget from the itinerary's source-bound facts.

    - flights: cheapest option's price x travelers
    - hotel: cheapest option's nightly price x nights (from the dates)
    Amounts are normalized to USD; a fact in an unknown currency sets
    ``mixed_currency`` rather than being silently included at face value.
    Attractions carry no price data in the tools, so they are not costed.

    When the user stated a ``budget_cap`` (in ``budget_currency``), the total is
    also expressed in that home currency and compared against the cap, so an
    over-budget trip is flagged honestly instead of shown as if it fits.
    """
    n_travelers = travelers or itinerary.get("travelers") or 1
    nights = trip_nights(itinerary.get("start_date"), itinerary.get("end_date"))
    items: List[dict] = []
    mixed_currency = False

    # Only positive prices are real options — a 0/None price is missing data, not a
    # free flight/room, and must never win the "cheapest" comparison.
    flights = [f for f in itinerary.get("flights", []) if (f.get("price") or 0) > 0]
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

    hotels = [h for h in itinerary.get("hotels", []) if (h.get("price_per_night") or 0) > 0]
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

    result: ComputedBudget = {
        "currency": "USD",
        "items": items,
        "total": total,
        "nights": nights,
        "travelers": n_travelers,
        "mixed_currency": mixed_currency,
        "cap": None,
        "cap_currency": None,
        "home_currency": None,
        "total_home": None,
        "cap_home": None,
        "fx_rate": None,
        "fx_note": None,
        "over_budget": None,
        "over_by_home": None,
        "assessment": None,
    }

    # Home-currency display + adherence. Home currency is the one the user stated
    # their budget in; if they gave none, we don't assume one (USD only). The USD→home
    # rate is a live, 24h-cached FX rate (static fallback), not a hardcoded constant.
    cap = budget_cap if budget_cap is not None else itinerary.get("budget_cap")
    home = normalize_currency(budget_currency or itinerary.get("budget_currency"))

    rate: Optional[float] = None
    if home and home != "USD":
        from fx import usd_to  # lazy import: keeps this module import-cycle-free

        r, is_live = usd_to(home)
        if r and r > 0:
            rate = r
            result["home_currency"] = home
            result["total_home"] = round(total * rate, 2)
            result["fx_rate"] = round(rate, 2)
            result["fx_note"] = (
                "Live rate, cached daily — verify before booking."
                if is_live
                else "Approximate rate (live rate unavailable) — verify before booking."
            )

    if cap and cap > 0 and total > 0:
        in_home = bool(home and rate)
        result["cap"] = cap
        result["cap_currency"] = home or "USD"
        cap_usd = (cap / rate) if in_home else (cap if not home else None)
        if cap_usd is not None:
            over = total > cap_usd
            result["over_budget"] = over
            disp_ccy = home if in_home else "USD"
            total_disp = result["total_home"] if in_home else total
            cap_disp = cap if in_home else cap_usd
            result["cap_home"] = cap_disp if in_home else None
            result["over_by_home"] = round(total_disp - cap_disp, 2)
            if over:
                result["assessment"] = (
                    f"Over budget by ~{_fmt_money(total_disp - cap_disp, disp_ccy)} "
                    f"(est. {_fmt_money(total_disp, disp_ccy)} vs your "
                    f"{_fmt_money(cap_disp, disp_ccy)} budget)."
                )
            else:
                result["assessment"] = (
                    f"Within budget — about {_fmt_money(cap_disp - total_disp, disp_ccy)} "
                    f"to spare (est. {_fmt_money(total_disp, disp_ccy)} of your "
                    f"{_fmt_money(cap_disp, disp_ccy)})."
                )

    return result
