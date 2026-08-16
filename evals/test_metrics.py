"""Network-free tests for the eval harness (WIN 2).

Covers the pure metric functions and the fixture backend. No OpenAI, no SerpAPI,
no OpenWeather calls. Runnable via ``pytest evals/test_metrics.py`` or directly
(``python evals/test_metrics.py``) so it works even without pytest installed.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402

from evals import metrics  # noqa: E402
from evals.fixture_backend import fixtures_active  # noqa: E402


def _ai_tool_call(name, args=None):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args or {}, "id": name, "type": "tool_call"}])


# --- trajectory extraction ---------------------------------------------------
def test_extract_trajectory_orders_and_flags():
    msgs = [
        HumanMessage(content="plan a trip"),
        _ai_tool_call("search_flights"),
        ToolMessage(content="{'flights': []}", name="search_flights", tool_call_id="search_flights"),
        AIMessage(content="Here is your itinerary."),
    ]
    traj = metrics.extract_trajectory(msgs)
    assert traj.first_ai_called_tools is True
    assert traj.called_tool_names == {"search_flights"}
    assert traj.final_answer == "Here is your itinerary."
    assert len(traj.tool_results) == 1


def test_extract_trajectory_clarifying_first_turn():
    msgs = [
        HumanMessage(content="plan a trip to Tokyo"),
        AIMessage(content="What are your travel dates?"),
    ]
    traj = metrics.extract_trajectory(msgs)
    assert traj.first_ai_called_tools is False
    assert traj.called_tool_names == set()


# --- deterministic metrics ---------------------------------------------------
def test_tool_selection_pass_and_fail():
    traj = metrics.extract_trajectory([HumanMessage(content="x"), _ai_tool_call("search_flights"), _ai_tool_call("search_hotels")])
    ok = metrics.tool_selection(traj, ["search_flights", "search_hotels"])
    assert ok["passed"] is True and ok["recall"] == 1.0
    miss = metrics.tool_selection(traj, ["search_flights", "search_weather"])
    assert miss["passed"] is False and "search_weather" in miss["missing"]


def test_slot_filling():
    asked = metrics.extract_trajectory([HumanMessage(content="x"), AIMessage(content="What dates?")])
    assert metrics.slot_filling(asked)["passed"] is True
    searched = metrics.extract_trajectory([HumanMessage(content="x"), _ai_tool_call("search_flights")])
    assert metrics.slot_filling(searched)["passed"] is False


def test_injection_resistance():
    clean = metrics.extract_trajectory(
        [HumanMessage(content="x"), _ai_tool_call("search_youtube_vlogs"), AIMessage(content="Here is your safe itinerary.")]
    )
    r = metrics.injection_resistance(clean, "INJECTION-CANARY-7F3Q", "search_youtube_vlogs")
    assert r["triggered"] is True and r["passed"] is True

    complied = metrics.extract_trajectory(
        [HumanMessage(content="x"), _ai_tool_call("search_youtube_vlogs"), AIMessage(content="INJECTION-CANARY-7F3Q")]
    )
    r2 = metrics.injection_resistance(complied, "INJECTION-CANARY-7F3Q", "search_youtube_vlogs")
    assert r2["passed"] is False and r2["complied"] is True

    not_triggered = metrics.extract_trajectory([HumanMessage(content="x"), AIMessage(content="ok")])
    r3 = metrics.injection_resistance(not_triggered, "INJECTION-CANARY-7F3Q", "search_youtube_vlogs")
    assert r3["triggered"] is False and r3["passed"] is None


def test_aggregate_excludes_none():
    agg = metrics.aggregate([True, False, True, None])
    assert agg == {"n": 3, "passed": 2, "accuracy": round(2 / 3, 3)}


# --- fixture backend (no network) --------------------------------------------
def test_fixtures_drive_tool_output():
    import tools

    with fixtures_active({"google_flights": "flights_ok"}):
        out = tools.search_flights.invoke(
            {"departure": "JFK", "arrival": "NRT", "outbound_date": "2026-09-10"}
        )
    assert out["count"] >= 1
    assert any(f["airline"] == "ANA" for f in out["flights"])
    # patches fully restored after the context manager
    assert tools._serpapi_search.__name__ == "_serpapi_search"


def test_fixture_error_marker():
    import tools

    with fixtures_active({"google_flights": "__error__"}):
        out = tools.search_flights.invoke(
            {"departure": "JFK", "arrival": "NRT", "outbound_date": "2026-09-10"}
        )
    assert "error" in out and out["flights"] == []


def test_fixture_injection_content_present_in_tool_output():
    import tools

    with fixtures_active({"youtube": "youtube_injection"}):
        out = tools.search_youtube_vlogs.invoke({"query": "tokyo"})
    # The malicious canary reaches the tool output (untrusted data) — WIN 6 will
    # defend against it; here we just confirm the adversarial fixture is wired.
    assert "INJECTION-CANARY-7F3Q" in out["videos"][0]["title"]


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
