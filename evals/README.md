# Eval + fixture harness (WIN 2)

The measurement backbone for the reliability upgrade. It runs the **real** agent
against **frozen tool fixtures**, so runs are deterministic and cost **no**
SerpAPI / OpenWeather spend. (The agent's own LLM calls and the abstention judge
do use OpenAI tokens.)

## Run it

```bash
python -m evals.run_eval --version baseline            # full golden set
python -m evals.run_eval --version baseline --limit 2  # first 2 scenarios
python -m evals.run_eval --version baseline --types simple,multi_constraint
python -m evals.run_eval --version baseline --no-judge # skip LLM judges
```

Writes a timestamped report to `evals/reports/` and prints a scoreboard.

## Metrics

| Metric | How | Status |
|---|---|---|
| **tool_selection** | deterministic — did it call the expected tools? | live |
| **slot_filling** | deterministic — did it ask before searching when underspecified? | live |
| **abstention** | LLM judge (judge ≠ generator) — honest when a tool failed? | live |
| **injection** | deterministic canary — did it ignore instructions in tool output? | live |
| **groundedness** | deterministic — every structured fact's `source_tool` was called AND its identifying value appears in that tool's result | live (WIN 3) |
| **budget_math** | stated total == computed total | pending WIN 4 |

## How fixtures work

`fixture_backend.py` monkeypatches the tools' network boundaries
(`tools._serpapi_search`, `tools.requests`, the disk cache) so they return frozen
JSON from `evals/fixtures/` instead of hitting the network. Each tool's real
parsing code still runs against the frozen raw response, so the eval exercises
production code.

- A scenario's `fixtures` map wires each engine (`google_flights`, `google_hotels`,
  `google_maps`, `youtube`, `google_ai_mode`, `weather`) to a fixture stem.
- `"__error__"` simulates an upstream tool failure (for abstention scenarios).
- Adversarial fixtures (`*_injection.json`) embed a canary instruction to test
  injection resistance.

> **Fixtures are Tokyo-themed.** A trip scenario's destination should match the
> fixture content, otherwise synthesis may (correctly) omit mismatched facts and
> produce an empty itinerary. To add other destinations, capture/author
> destination-specific fixtures and point new scenarios at them.

To record real responses instead of the hand-authored ones:

```bash
python -m evals.capture_fixtures   # spends SerpAPI/OpenWeather quota
```

## Golden set

`golden.jsonl` — scenarios typed `simple`, `underspecified`, `multi_constraint`,
`tool_error`, `injection`. Every bug found later should become a new golden row
(see plan-v2.md §6, `docs/failure_modes.md`).

## Tests

`test_metrics.py` — network-free unit tests for the metrics and fixture backend:

```bash
python evals/test_metrics.py    # or: pytest evals/test_metrics.py
```
