"""Fixture injection for deterministic, zero-external-spend eval runs (WIN 2).

Real tool calls hit SerpAPI / OpenWeather, whose responses change hourly and cost
money — useless for reproducible evals. This module monkeypatches the tools'
network choke points so they return *frozen* fixture responses instead:

- ``tools._serpapi_search`` (the single wrapper behind flights, hotels, maps,
  YouTube and AI-mode search) is replaced with a fixture reader.
- ``tools.requests`` is shimmed so ``search_weather``'s POST returns a fixture.
- the disk cache is bypassed so fixtures always drive the result.

Crucially we patch at the *raw response* boundary, so each tool's real parsing
code still runs against the frozen response — the eval exercises production code,
not a reimplementation.

Usage::

    with fixtures_active({"google_flights": "flights_ok", "weather": "weather_ok"}):
        app.invoke(...)
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional

import tools

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

# Sentinel fixture name that simulates an upstream tool failure.
ERROR_FIXTURE = "__error__"

# Minimal empty-but-valid raw responses, so a tool called without a configured
# fixture degrades gracefully (returns "no results") rather than crashing.
_EMPTY_BY_ENGINE: Dict[str, Dict[str, Any]] = {
    "google_flights": {"best_flights": [], "other_flights": []},
    "google_hotels": {"properties": []},
    "google_maps": {"local_results": []},
    "youtube": {"video_results": []},
    "google_ai_mode": {"text_blocks": []},
}

# The active engine -> fixture-name mapping for the scenario currently running.
_active: Dict[str, str] = {}


def _load(name: str) -> Dict[str, Any]:
    path = _FIXTURE_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Fixture not found: {path}")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


# --- Fake network boundaries -------------------------------------------------
def _fake_serpapi_search(
    params: Dict[str, Any], cache_key_prefix: str = "", ttl_hours=None
) -> Dict[str, Any]:
    engine = params.get("engine", "")
    name = _active.get(engine)
    if name is None:
        return _EMPTY_BY_ENGINE.get(engine, {})
    if name == ERROR_FIXTURE:
        return {"error": f"simulated upstream failure for engine '{engine}'"}
    return _load(name)


class _FakeResponse:
    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def raise_for_status(self) -> None:  # pragma: no cover - trivial
        return None

    def json(self) -> Dict[str, Any]:
        return self._data


class _RequestsShim:
    """Delegates everything to real ``requests`` except ``post`` (fixture-backed)."""

    def __init__(self, real):
        self._real = real

    def post(self, *args, **kwargs) -> _FakeResponse:
        name = _active.get("weather")
        if name == ERROR_FIXTURE:
            raise self._real.exceptions.RequestException("simulated weather API failure")
        data = _load(name) if name else {"answer": "No forecast available."}
        return _FakeResponse(data)

    def __getattr__(self, item):  # pragma: no cover - passthrough
        return getattr(self._real, item)


def _noop_get_cached(key: str) -> Optional[Any]:
    return None


def _noop_set_cached(key: str, value: Any, expiry_hours: int = 6) -> None:
    return None


@contextmanager
def fixtures_active(mapping: Optional[Dict[str, str]]):
    """Install fixture-backed tool boundaries for the duration of the block.

    ``mapping`` maps a SerpAPI engine name (or "weather") to a fixture file stem,
    or to ``ERROR_FIXTURE`` to simulate a tool failure.
    """
    global _active
    saved = {
        "_serpapi_search": tools._serpapi_search,
        "requests": tools.requests,
        "get_cached": tools.get_cached,
        "set_cached": tools.set_cached,
        "_active": _active,
    }
    _active = dict(mapping or {})
    tools._serpapi_search = _fake_serpapi_search
    tools.requests = _RequestsShim(saved["requests"])
    tools.get_cached = _noop_get_cached
    tools.set_cached = _noop_set_cached
    try:
        yield
    finally:
        tools._serpapi_search = saved["_serpapi_search"]
        tools.requests = saved["requests"]
        tools.get_cached = saved["get_cached"]
        tools.set_cached = saved["set_cached"]
        _active = saved["_active"]
