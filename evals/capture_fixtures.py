"""Record REAL raw tool responses as fixtures (optional, run manually).

The eval harness ships with hand-authored, realistic fixtures so it runs out of
the box with no external spend. To capture genuine SerpAPI / OpenWeather
responses instead (more representative shapes), run this once with real keys in
your environment:

    python -m evals.capture_fixtures

It writes raw responses to evals/fixtures/captured/. Review them, then copy the
ones you want over the hand-authored fixtures. This DOES spend SerpAPI /
OpenWeather quota, so it is never run as part of an eval.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import tools  # noqa: E402

_OUT = _PROJECT_ROOT / "evals" / "fixtures" / "captured"

# (fixture_stem, serpapi params) — mirrors what each tool sends.
_SERP_CAPTURES = [
    ("flights_ok", {"engine": "google_flights", "departure_id": "JFK", "arrival_id": "NRT",
                    "outbound_date": "2026-09-10", "adults": 2, "currency": "USD", "hl": "en", "type": "2"}),
    ("hotels_ok", {"engine": "google_hotels", "q": "Tokyo, Japan", "check_in_date": "2026-09-10",
                   "check_out_date": "2026-09-15", "adults": 2, "currency": "USD", "gl": "us", "hl": "en", "sort_by": "3"}),
    ("attractions_ok", {"engine": "google_maps", "q": "tourist_attraction in Tokyo, Japan", "type": "search", "hl": "en"}),
    ("youtube_ok", {"engine": "youtube", "search_query": "Tokyo travel guide 2026", "hl": "en"}),
    ("ai_mode_ok", {"engine": "google_ai_mode", "q": "best time to visit Tokyo", "hl": "en"}),
]


def main() -> int:
    _OUT.mkdir(parents=True, exist_ok=True)
    for stem, params in _SERP_CAPTURES:
        print(f"Capturing {stem} ...")
        raw = tools._serpapi_search(dict(params), stem)
        (_OUT / f"{stem}.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")

    print("Capturing weather_ok ...")
    weather = tools.search_weather.invoke(
        {"location": "Tokyo, Japan", "start_date": "2026-09-10", "end_date": "2026-09-15"}
    )
    (_OUT / "weather_raw.json").write_text(json.dumps(weather, indent=2), encoding="utf-8")

    print(f"\nDone. Review captures in {_OUT.relative_to(_PROJECT_ROOT)} and copy the ones you want.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
