"""Network-free tests for WIN 5 tool hardening (cache key, validation, freshness).

No SerpAPI / OpenWeather / OpenAI calls. Run: ``python evals/test_tools_hardening.py``
or ``pytest evals/test_tools_hardening.py``.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import tools  # noqa: E402


def test_stable_cache_key_is_order_independent_and_excludes_api_key():
    k1 = tools._stable_cache_key("flights", {"a": 1, "b": 2, "api_key": "secret"})
    k2 = tools._stable_cache_key("flights", {"b": 2, "a": 1, "api_key": "different"})
    assert k1 == k2  # order- and api_key-independent
    assert "secret" not in k1 and k1.startswith("flights:")
    k3 = tools._stable_cache_key("flights", {"a": 1, "b": 3})
    assert k3 != k1  # different params -> different key


def test_validate_serpapi():
    assert tools._validate_serpapi({"best_flights": []}) is None
    assert tools._validate_serpapi({"error": "boom"}) == "boom"
    assert tools._validate_serpapi({"search_metadata": {"status": "Error"}}) is not None
    assert tools._validate_serpapi("not a dict") is not None


def test_weather_horizon():
    today = datetime.now(timezone.utc).date()
    near = (today + timedelta(days=3)).isoformat()
    far = (today + timedelta(days=90)).isoformat()
    is_fc_near, days_near = tools._weather_horizon(near)
    is_fc_far, days_far = tools._weather_horizon(far)
    assert is_fc_near is True and 0 <= days_near <= 14
    assert is_fc_far is False and days_far > 14
    assert tools._weather_horizon("not-a-date") == (None, None)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"[PASS] {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[FAIL] {fn.__name__} — {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
