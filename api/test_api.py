"""Test for the agent→SSE streaming pipeline (WIN 9.1).

This is the only non-trivial, regression-prone part that runs without live
Supabase: `stream_agent` driving the real graph via `astream`, filtering to the
answer tokens, capturing the verified itinerary, and emitting typed SSE events.
Auth/persistence are standard plumbing, verified against live Supabase (see
docs/win-9-scope.md).

Run: `python api/test_api.py` (needs OPENAI key) or pytest.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from langgraph.checkpoint.memory import MemorySaver

from api.streaming import stream_agent
from backend import build_graph
from evals.fixture_backend import fixtures_active


def test_stream_agent_emits_token_itinerary_done():
    graph = build_graph(checkpointer=MemorySaver())
    fixtures = {
        "google_flights": "flights_ok", "google_hotels": "hotels_ok",
        "weather": "weather_ok", "google_maps": "attractions_ok",
    }
    query = ("Plan a 5-day trip to Tokyo from New York, Sep 10-15 2026, 2 adults, "
             "budget 4000. Flights, hotel, weather, things to do.")

    async def collect():
        frames = []
        with fixtures_active(fixtures):
            async for frame in stream_agent(graph, "test-thread", query):
                frames.append(frame)
        return frames

    frames = asyncio.run(collect())
    events = [f.split("\n", 1)[0].removeprefix("event: ") for f in frames]
    assert "token" in events, "expected streamed answer tokens"
    assert "itinerary" in events, "expected a structured itinerary event"
    assert events[-1] == "done" and "error" not in events


if __name__ == "__main__":
    try:
        test_stream_agent_emits_token_itinerary_done()
        print("[PASS] test_stream_agent_emits_token_itinerary_done\n1/1 passed")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        raise SystemExit(1)
