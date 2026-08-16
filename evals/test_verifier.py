"""Network-free tests for the WIN 7 value-level verifier (use_llm=False)."""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402

import verifier  # noqa: E402


def _messages():
    return [
        HumanMessage(content="plan trip"),
        ToolMessage(content="{'flights': [{'airline': 'ANA', 'price': 812}]}", name="search_flights", tool_call_id="1"),
        ToolMessage(content="{'hotels': [{'name': 'Shinjuku Granbell Hotel', 'price': 142}]}", name="search_hotels", tool_call_id="2"),
        ToolMessage(content="{'attractions': [{'name': 'Senso-ji Temple'}]}", name="search_attractions", tool_call_id="3"),
        AIMessage(content="done"),
    ]


def test_keeps_supported_facts():
    itin = {
        "flights": [{"airline": "ANA", "price": 812, "source_tool": "search_flights"}],
        "hotels": [{"name": "Shinjuku Granbell Hotel", "price_per_night": 142, "source_tool": "search_hotels"}],
        "attractions": [{"name": "Senso-ji Temple", "source_tool": "search_attractions"}],
        "weather": [],
    }
    pruned, report = verifier.verify_itinerary(itin, _messages(), use_llm=False)
    assert report["n_removed"] == 0 and report["status"] == "verified"
    assert len(pruned["flights"]) == 1 and len(pruned["hotels"]) == 1


def test_removes_fabricated_price_and_name():
    itin = {
        "flights": [{"airline": "ANA", "price": 9999, "source_tool": "search_flights"}],  # price not in result
        "hotels": [{"name": "Ghost Palace Hotel", "price_per_night": 142, "source_tool": "search_hotels"}],  # name absent
        "attractions": [],
        "weather": [],
    }
    pruned, report = verifier.verify_itinerary(itin, _messages(), use_llm=False)
    assert pruned["flights"] == [] and pruned["hotels"] == []
    assert report["n_removed"] == 2 and report["status"] == "flagged"
    reasons = {r["reason"] for r in report["removed"]}
    assert "price not in tool result" in reasons and "name not in tool result" in reasons
    assert report["disclaimers"]  # abstention disclaimers present


def test_removes_facts_from_uncalled_tool():
    itin = {"flights": [], "hotels": [], "attractions": [],
            "weather": [{"summary": "sunny", "source_tool": "search_weather"}]}  # weather never called
    pruned, report = verifier.verify_itinerary(itin, _messages(), use_llm=False)
    assert pruned["weather"] == [] and report["n_removed"] == 1
    assert report["removed"][0]["reason"] == "source tool not called/errored"


def test_tolerates_name_normalization():
    msgs = [
        HumanMessage(content="x"),
        ToolMessage(content="{'flights': [{'airline': 'United, United', 'price': 1150}]}", name="search_flights", tool_call_id="1"),
        AIMessage(content="done"),
    ]
    itin = {"flights": [{"airline": "United Airlines", "price": 1150, "source_tool": "search_flights"}],
            "hotels": [], "attractions": [], "weather": []}
    pruned, report = verifier.verify_itinerary(itin, msgs, use_llm=False)
    assert len(pruned["flights"]) == 1 and report["n_removed"] == 0


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
