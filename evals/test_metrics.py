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

import compute  # noqa: E402
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


# --- groundedness (WIN 3) ----------------------------------------------------
def _traj_with_results():
    msgs = [
        HumanMessage(content="x"),
        _ai_tool_call("search_flights"),
        ToolMessage(content="{'flights': [{'airline': 'ANA', 'price': 812}]}", name="search_flights", tool_call_id="1"),
        _ai_tool_call("search_hotels"),
        ToolMessage(content="{'hotels': [{'name': 'Shinjuku Granbell Hotel'}]}", name="search_hotels", tool_call_id="2"),
        _ai_tool_call("search_attractions"),
        ToolMessage(content="{'attractions': [{'name': 'Senso-ji Temple'}]}", name="search_attractions", tool_call_id="3"),
        AIMessage(content="done"),
    ]
    return metrics.extract_trajectory(msgs)


def test_groundedness_all_grounded_and_ignores_day_prose():
    itin = {
        "flights": [{"airline": "ANA", "source_tool": "search_flights"}],
        "hotels": [{"name": "Shinjuku Granbell Hotel", "source_tool": "search_hotels"}],
        "attractions": [{"name": "Senso-ji Temple", "source_tool": "search_attractions"}],
        "weather": [],
        # day-plan prose must NOT be scored as facts
        "days": [{"day": 1, "activities": ["Check into hotel", "Dinner in Shibuya"]}],
    }
    r = metrics.groundedness(itin, _traj_with_results())
    assert r["score"] == 1.0 and r["passed"] is True and r["n_facts"] == 3


def test_groundedness_flags_fabricated_and_misattributed():
    itin = {
        "flights": [{"airline": "Fake Air", "source_tool": "search_flights"}],  # value absent from result
        "hotels": [{"name": "Ghost Hotel", "source_tool": "search_hotels"}],  # value absent from result
        "weather": [{"summary": "sunny", "source_tool": "search_weather"}],  # tool never called
        "days": [],
    }
    r = metrics.groundedness(itin, _traj_with_results())
    assert r["score"] == 0.0 and r["passed"] is False and len(r["ungrounded"]) == 3


def test_groundedness_tolerates_name_normalization():
    # Fixture says "United"; the LLM writes "United Airlines" — still grounded.
    msgs = [
        HumanMessage(content="x"),
        _ai_tool_call("search_flights"),
        ToolMessage(content="{'flights': [{'airline': 'United, United'}]}", name="search_flights", tool_call_id="1"),
        AIMessage(content="done"),
    ]
    traj = metrics.extract_trajectory(msgs)
    grounded = metrics.groundedness({"flights": [{"airline": "United Airlines", "source_tool": "search_flights"}]}, traj)
    assert grounded["passed"] is True and grounded["score"] == 1.0
    fabricated = metrics.groundedness({"flights": [{"airline": "Fake Air", "source_tool": "search_flights"}]}, traj)
    assert fabricated["passed"] is False and fabricated["score"] == 0.0


def test_groundedness_no_itinerary():
    r = metrics.groundedness(None, metrics.extract_trajectory([HumanMessage(content="x")]))
    assert r["passed"] is None and r["score"] is None


def test_groundedness_zero_facts_is_excluded_not_failed():
    # An itinerary with no source-bound facts has nothing to score -> excluded.
    r = metrics.groundedness({"flights": [], "hotels": [], "weather": [], "attractions": []}, _traj_with_results())
    assert r["passed"] is None and r["score"] is None and r["n_facts"] == 0


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


# --- deterministic compute (WIN 4) -------------------------------------------
def test_trip_nights():
    assert compute.trip_nights("2026-09-10", "2026-09-15") == 5
    assert compute.trip_nights("2026-09-10", "2026-09-10") is None  # zero nights
    assert compute.trip_nights(None, "2026-09-15") is None
    assert compute.trip_nights("bad", "2026-09-15") is None


def test_compute_budget_cheapest_and_math():
    itin = {
        "start_date": "2026-09-10",
        "end_date": "2026-09-15",  # 5 nights
        "travelers": 2,
        "flights": [{"airline": "ANA", "price": 812}, {"airline": "JAL", "price": 905}],
        "hotels": [{"name": "Cheap Inn", "price_per_night": 100}, {"name": "Pricey", "price_per_night": 200}],
    }
    b = compute.compute_budget(itin)
    # cheapest flight 812 x 2 travelers + cheapest hotel 100 x 5 nights
    assert b["total"] == round(812 * 2 + 100 * 5, 2)
    assert b["total"] == round(sum(i["amount"] for i in b["items"]), 2)
    assert b["nights"] == 5 and b["travelers"] == 2 and b["mixed_currency"] is False


def test_compute_budget_flags_unknown_currency():
    itin = {"start_date": "2026-09-10", "end_date": "2026-09-12", "travelers": 1,
            "flights": [{"airline": "X", "price": 500, "currency": "XYZ"}], "hotels": []}
    b = compute.compute_budget(itin)
    assert b["mixed_currency"] is True and b["items"] == []


# --- budget_math metric (WIN 4) ----------------------------------------------
def test_budget_math_consistent():
    itin = {"budget": {"currency": "USD", "total": 1624.0,
                       "items": [{"label": "Flights", "amount": 1624.0}]}}
    r = metrics.budget_math(itin)
    assert r["passed"] is True and r["total_matches_sum"] is True


def test_budget_math_total_mismatch_fails():
    # LLM echoed the user's cap (2500) but items sum to 2219 — the real WIN 3 bug.
    itin = {"budget": {"currency": "USD", "total": 2500.0,
                       "items": [{"label": "Flights", "amount": 1624.0}, {"label": "Hotel", "amount": 595.0}]}}
    r = metrics.budget_math(itin)
    assert r["passed"] is False and r["sum_items"] == 2219.0


def test_budget_math_missing_total_fails():
    itin = {"budget": {"items": [{"label": "Flights", "amount": 500.0}]}}
    assert metrics.budget_math(itin)["passed"] is False


def test_budget_math_no_items_excluded():
    assert metrics.budget_math({"budget": {"items": []}})["passed"] is None
    assert metrics.budget_math(None)["passed"] is None


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
