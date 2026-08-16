"""Network-free tests for WIN 8 observability (cost accounting + tracing toggle)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import observability  # noqa: E402


def test_price_for_exact_and_prefix():
    assert observability._price_for("gpt-4o")["input"] == 2.50
    assert observability._price_for("gpt-4o-2024-08-06") == observability._price_for("gpt-4o")
    assert observability._price_for("gpt-4o-mini")["output"] == 0.60
    assert observability._price_for("totally-unknown-model") == {"input": 0.0, "output": 0.0}


def test_longest_prefix_wins_mini_not_4o():
    # "gpt-4o-mini-..." must resolve to gpt-4o-mini, not gpt-4o (the earlier bug).
    assert observability._price_for("gpt-4o-mini-2024-07-18") == observability._price_for("gpt-4o-mini")
    assert observability._price_for("gpt-5.4-nano")["output"] == 1.25


def test_cost_credits_cached_input():
    usage = {"gpt-4o": {"input_tokens": 1_000_000, "output_tokens": 0,
                        "input_token_details": {"cache_read": 1_000_000}}}
    # all input cached -> 1M * $2.50 * 0.5 discount = $1.25
    cost = observability.compute_cost(usage)
    assert cost["total_usd"] == 1.25 and cost["cached_input_tokens"] == 1_000_000


def test_compute_cost():
    usage = {
        "gpt-4o": {"input_tokens": 1_000_000, "output_tokens": 500_000},
        "gpt-4o-mini": {"input_tokens": 2_000_000, "output_tokens": 1_000_000},
    }
    cost = observability.compute_cost(usage)
    # gpt-4o: 1*2.50 + 0.5*10 = 7.50 ; mini: 2*0.15 + 1*0.60 = 0.90 -> 8.40
    assert cost["total_usd"] == 8.40
    assert cost["input_tokens"] == 3_000_000 and cost["output_tokens"] == 1_500_000
    assert cost["by_model"]["gpt-4o"]["cost_usd"] == 7.5


def test_compute_cost_empty():
    assert observability.compute_cost({})["total_usd"] == 0.0
    assert observability.compute_cost(None)["total_usd"] == 0.0


def test_configure_tracing_returns_bool_and_sets_env_when_on():
    enabled = observability.configure_tracing()
    assert isinstance(enabled, bool)
    if enabled:  # .env has LANGSMITH_TRACING=true in this project
        assert os.environ.get("LANGSMITH_TRACING") == "true"
        assert os.environ.get("LANGSMITH_PROJECT")


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
