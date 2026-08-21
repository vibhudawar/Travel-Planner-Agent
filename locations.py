"""Airport/location resolution from an offline dataset (airportsdata).

Production-style location resolution: a natural-language place ("delhi", "bali",
"lon") becomes structured airport candidates (IATA code + city/country + coords).
Used by the frontend autocomplete (user disambiguates multi-airport cities) and as
a deterministic safety net inside ``search_flights``. No API key; ~7.9k commercial
airports; refresh with ``pip install -U airportsdata``.

This replaces the earlier hand-maintained city→code dict: the dataset is the source
of truth, the small ``_PRIMARY_HUB`` map only breaks ties for big multi-airport
cities (which airport a bare city name should default to).
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import List, Optional, TypedDict

import airportsdata

# For big multi-airport cities, the primary international hub a bare city name
# should resolve to (the dataset has no passenger-traffic ranking to infer this).
_PRIMARY_HUB = {
    "london": "LHR", "new york": "JFK", "tokyo": "HND", "paris": "CDG",
    "moscow": "SVO", "chicago": "ORD", "washington": "IAD", "houston": "IAH",
    "sao paulo": "GRU", "milan": "MXP", "istanbul": "IST", "bangkok": "BKK",
    "delhi": "DEL", "new delhi": "DEL", "mumbai": "BOM", "shanghai": "PVG",
    "beijing": "PEK", "seoul": "ICN", "osaka": "KIX", "jakarta": "CGK",
    "bali": "DPS", "dubai": "DXB", "rome": "FCO", "berlin": "BER",
    "toronto": "YYZ", "los angeles": "LAX",
}

# Common alternate/local city names -> the dataset's canonical city name. The
# dataset stores one name per city ("Cochin", not "Kochi"), so map aliases before
# matching. This is a name-normalization layer, not a code dict.
_CITY_ALIASES = {
    "kochi": "cochin", "bengaluru": "bangalore", "bombay": "mumbai",
    "madras": "chennai", "calcutta": "kolkata", "gurugram": "gurgaon",
    "prayagraj": "allahabad", "vadodara": "baroda", "puducherry": "pondicherry",
    "saigon": "ho chi minh city", "bali": "denpasar", "new delhi": "delhi",
    "peking": "beijing", "rangoon": "yangon", "goa": "dabolim",
}


class Location(TypedDict):
    iata: str
    name: str
    city: str
    country: str
    lat: float
    lon: float
    label: str


def _norm(value) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(value or "").lower())).strip()


@lru_cache(maxsize=1)
def _airports() -> list:
    data = airportsdata.load("IATA")
    out = []
    for code, a in data.items():
        if not code or not a.get("city"):
            continue
        out.append(
            {
                "iata": code, "name": a["name"], "city": a["city"], "country": a["country"],
                "lat": a["lat"], "lon": a["lon"],
                "_city": _norm(a["city"]), "_name": _norm(a["name"]), "_code": code.lower(),
            }
        )
    return out


@lru_cache(maxsize=1)
def _codes() -> set:
    return {a["iata"] for a in _airports()}


def _to_location(a) -> Location:
    return {
        "iata": a["iata"], "name": a["name"], "city": a["city"], "country": a["country"],
        "lat": a["lat"], "lon": a["lon"],
        "label": f"{a['city']} — {a['name']} ({a['iata']}), {a['country']}",
    }


def _canonical(query: str) -> str:
    """Normalize + apply city aliases (Kochi->Cochin), dropping a country suffix and
    any parenthetical code. Split/strip on the RAW string — _norm removes the comma,
    so this must run before normalizing (else 'Hanoi, Vietnam' never truncates)."""
    head = re.sub(r"\(.*?\)", "", str(query or "").split(",")[0])
    q = _norm(head)
    return _CITY_ALIASES.get(q, q)


def search_locations(query: str, limit: int = 8) -> List[Location]:
    """Ranked airport candidates for a query (for autocomplete). Best match first."""
    raw = _norm(query)
    if not raw:
        return []
    airports = _airports()
    q = _canonical(query)
    scored = []
    for a in airports:
        if a["_city"] == q:
            score = 100
        elif a["_city"].startswith(q):
            score = 80
        elif q in a["_city"]:
            score = 60
        elif a["_name"].startswith(q):
            score = 50
        elif q in a["_name"]:
            score = 40
        else:
            score = 0
        # A 3-letter query can be an exact code — a strong candidate, but a full
        # city-name match still outranks it (so "leh"->IXL beats LEH/Le Havre,
        # while "goa"->Genova still appears below Goa's own airport).
        if len(raw) == 3 and a["_code"] == raw:
            score = max(score, 95)
        if not score:
            continue
        if _PRIMARY_HUB.get(a["_city"]) == a["iata"]:
            score += 15  # float the primary hub to the top of a city's airports
        # Tie-break: shorter city name is a closer match to the typed prefix
        # (so "London" outranks "Londolovit" for the query "lond").
        scored.append((score, len(a["_city"]), a["city"], a["iata"], a))
    scored.sort(key=lambda t: (-t[0], t[1], t[2], t[3]))
    return [_to_location(t[4]) for t in scored[:limit]]


def resolve_iata(query: str) -> Optional[str]:
    """Best single IATA code for a place (city name or code). None if unresolved."""
    if _canonical(query) in _PRIMARY_HUB:
        return _PRIMARY_HUB[_canonical(query)]
    results = search_locations(query, limit=1)
    return results[0]["iata"] if results else None
