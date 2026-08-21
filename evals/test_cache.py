"""Cache-correctness tests (WIN 9.2) — network-free.

The slot key is the correctness gate: it must group genuinely-equivalent requests
and separate ones that differ in a decision-relevant way (destination, dates,
travelers, budget band). The "$2000 plan for a $5000 request" failure class is the
headline case.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cache import budget_band, canonical_slot_key  # noqa: E402

_PASS = "[PASS]"


def _key(dest="Tokyo", start="2026-09-15", end="2026-09-20", travelers=2, cap=None, ccy="USD"):
    return canonical_slot_key({
        "destination": dest, "start_date": start, "end_date": end,
        "travelers": travelers, "budget_cap": cap, "budget_currency": ccy,
    })


def test_budget_band_buckets():
    assert budget_band(None) == "none"
    assert budget_band(0) == "none"
    assert budget_band(400) == "0-500"
    assert budget_band(2000) == "1750-3000"
    assert budget_band(5000) == "5000-8000"
    # similar budgets share a band; very different ones don't
    assert budget_band(2000) == budget_band(2100)
    assert budget_band(2000) != budget_band(5000)
    print(_PASS, "test_budget_band_buckets")


def test_same_trip_same_key():
    assert _key() == _key()
    assert _key() is not None
    print(_PASS, "test_same_trip_same_key")


def test_budget_band_separates_2000_vs_5000():
    # The headline correctness case: a $2000 request must NOT match a $5000 one.
    assert _key(cap=2000) != _key(cap=5000)
    # ...but near-equal budgets in the same band do match.
    assert _key(cap=2000) == _key(cap=2100)
    print(_PASS, "test_budget_band_separates_2000_vs_5000")


def test_decision_relevant_fields_separate_keys():
    base = _key()
    assert base != _key(dest="Kyoto")
    assert base != _key(travelers=4)
    assert base != _key(end="2026-09-25")  # different nights
    print(_PASS, "test_decision_relevant_fields_separate_keys")


def test_uncacheable_requests_return_none():
    assert canonical_slot_key({"destination": None, "start_date": "2026-09-15", "end_date": "2026-09-20"}) is None
    assert canonical_slot_key({"destination": "Tokyo", "start_date": None, "end_date": None}) is None
    # zero-night / inverted range is not derivable
    assert _key(start="2026-09-20", end="2026-09-20") is None
    print(_PASS, "test_uncacheable_requests_return_none")


def test_currency_normalized_into_band():
    # A budget in INR is converted to USD before banding, so ₹100000 (~$1163) lands
    # in a low band, well separated from a $5000 request.
    inr = _key(cap=100000, ccy="INR")
    assert inr is not None
    assert inr != _key(cap=5000, ccy="USD")
    print(_PASS, "test_currency_normalized_into_band")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\n{len(tests)}/{len(tests)} passed")
