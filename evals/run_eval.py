"""Eval harness orchestrator (plan-v2.md WIN 2).

Runs each golden scenario through the REAL agent against frozen fixtures, scores
trajectory + behavior metrics, writes a timestamped report, and prints a
scoreboard.

    python -m evals.run_eval --version baseline
    python -m evals.run_eval --version baseline --limit 2 --types simple
    python -m evals.run_eval --version baseline --no-judge   # skip LLM judges

The tool side is deterministic and free (fixtures); the agent's own LLM calls and
the abstention judge do use OpenAI tokens.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Allow both `python -m evals.run_eval` and `python evals/run_eval.py`.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from langchain_core.messages import HumanMessage  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

from backend import build_graph  # noqa: E402
from evals import judges, metrics  # noqa: E402
from evals.fixture_backend import fixtures_active  # noqa: E402
from settings import get_settings  # noqa: E402

_GOLDEN = _PROJECT_ROOT / "evals" / "golden.jsonl"
_REPORTS = _PROJECT_ROOT / "evals" / "reports"
_RECURSION_LIMIT = 18  # bound the agent loop so a confused run can't spin forever


def load_golden(path: Path = _GOLDEN) -> List[dict]:
    scenarios = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                scenarios.append(json.loads(line))
    return scenarios


def run_scenario(app, scenario: dict) -> dict:
    config = {
        "configurable": {"thread_id": f"eval-{scenario['id']}"},
        "recursion_limit": _RECURSION_LIMIT,
    }
    with fixtures_active(scenario.get("fixtures")):
        return app.invoke({"messages": [HumanMessage(content=scenario["query"])]}, config=config)


def score_scenario(
    scenario: dict, traj: metrics.Trajectory, itinerary: Optional[dict], use_judge: bool
) -> Dict[str, Any]:
    stype = scenario["type"]
    scored: Dict[str, Any] = {}

    if scenario.get("expected_tools"):
        scored["tool_selection"] = metrics.tool_selection(traj, scenario["expected_tools"])

    if stype == "underspecified":
        scored["slot_filling"] = metrics.slot_filling(traj)

    if stype in ("simple", "multi_constraint"):
        scored["groundedness"] = metrics.groundedness(itinerary, traj)
        scored["budget_math"] = metrics.budget_math(itinerary)

    if stype == "tool_error":
        if use_judge:
            scored["abstention"] = judges.judge_abstention(
                scenario["query"], scenario["error_tool"], traj.final_answer
            )
        else:
            scored["abstention"] = {"passed": None, "reason": "judge skipped (--no-judge)"}

    if stype == "injection":
        scored["injection"] = metrics.injection_resistance(
            traj, scenario["canary"], scenario.get("injected_tool")
        )

    return scored


def _passes_for(results: List[dict], metric: str, types: Optional[set] = None) -> List[Optional[bool]]:
    out = []
    for r in results:
        if types is not None and r["type"] not in types:
            continue
        m = r["metrics"].get(metric)
        if m is not None:
            out.append(m.get("passed"))
    return out


def _groundedness_summary(results: List[dict]) -> dict:
    """Aggregate groundedness: pass rate plus mean fact-level score."""
    entries = [r["metrics"]["groundedness"] for r in results if "groundedness" in r["metrics"]]
    scored = [e for e in entries if e.get("score") is not None]
    agg = metrics.aggregate([e.get("passed") for e in entries])
    mean_score = round(sum(e["score"] for e in scored) / len(scored), 3) if scored else None
    total_facts = sum(e.get("n_facts", 0) for e in scored)
    return {**agg, "mean_score": mean_score, "total_facts": total_facts}


def build_report(version: str, results: List[dict], use_judge: bool) -> dict:
    settings = get_settings()
    scoreboard = {
        "tool_selection": metrics.aggregate(
            _passes_for(results, "tool_selection", {"simple", "multi_constraint"})
        ),
        "slot_filling": metrics.aggregate(_passes_for(results, "slot_filling")),
        "abstention": metrics.aggregate(_passes_for(results, "abstention")),
        "injection": metrics.aggregate(_passes_for(results, "injection")),
        "groundedness": _groundedness_summary(results),
        "budget_math": metrics.aggregate(_passes_for(results, "budget_math", {"simple", "multi_constraint"})),
    }
    return {
        "version": version,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "generator_model": settings.openai_model,
        "judge_model": settings.judge_model if use_judge else None,
        "n_scenarios": len(results),
        "scoreboard": scoreboard,
        "scenarios": results,
    }


def print_scoreboard(report: dict) -> None:
    sb = report["scoreboard"]
    print("\n" + "=" * 60)
    print(f"  EVAL SCOREBOARD — version: {report['version']}")
    print(f"  generator={report['generator_model']}  judge={report['judge_model']}")
    print("=" * 60)
    print(f"  {'metric':<18}{'passed':>8}{'scored':>8}{'accuracy':>12}")
    print("  " + "-" * 44)
    for name in ("tool_selection", "slot_filling", "abstention", "injection", "groundedness", "budget_math"):
        m = sb[name]
        acc = "n/a" if m["accuracy"] is None else f"{m['accuracy']:.1%}"
        print(f"  {name:<18}{m['passed']:>8}{m['n']:>8}{acc:>12}")
    g = sb["groundedness"]
    if g.get("mean_score") is not None:
        print(f"  {'':<18}mean fact-level groundedness score: {g['mean_score']} over {g['total_facts']} facts")
    print("=" * 60)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Trip Planner eval harness.")
    parser.add_argument("--version", default="baseline", help="label for this run (scoreboard row)")
    parser.add_argument("--limit", type=int, default=None, help="run only the first N scenarios")
    parser.add_argument("--types", default=None, help="comma-separated scenario types to include")
    parser.add_argument("--no-judge", action="store_true", help="skip LLM-judge metrics (abstention)")
    args = parser.parse_args(argv)

    use_judge = not args.no_judge
    scenarios = load_golden()
    if args.types:
        wanted = {t.strip() for t in args.types.split(",")}
        scenarios = [s for s in scenarios if s["type"] in wanted]
    if args.limit is not None:
        scenarios = scenarios[: args.limit]

    if not scenarios:
        print("No scenarios matched the given filters.", file=sys.stderr)
        return 2

    print(f"Running {len(scenarios)} scenario(s)  (judge={'on' if use_judge else 'off'}) ...")
    app = build_graph(checkpointer=MemorySaver())

    results: List[dict] = []
    for scenario in scenarios:
        row: Dict[str, Any] = {"id": scenario["id"], "type": scenario["type"], "error": None}
        try:
            state = run_scenario(app, scenario)
            traj = metrics.extract_trajectory(state["messages"])
            itinerary = state.get("itinerary")
            row["metrics"] = score_scenario(scenario, traj, itinerary, use_judge)
            row["called_tools"] = sorted(traj.called_tool_names)
            row["has_itinerary"] = itinerary is not None
            row["itinerary"] = itinerary  # committed for audit / inspection
            row["final_answer_preview"] = (traj.final_answer or "")[:300]
        except Exception as exc:  # noqa: BLE001 - isolate a bad scenario, don't crash the run
            row["error"] = f"{type(exc).__name__}: {exc}"
            row["metrics"] = {}
        results.append(row)
        status = "ERROR" if row["error"] else "ok"
        print(f"  [{status}] {scenario['id']} ({scenario['type']}) — tools: {row.get('called_tools', [])}")
        if row["error"]:
            print(f"          {row['error']}")

    report = build_report(args.version, results, use_judge)
    _REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = report["timestamp"].replace(":", "").replace("-", "")
    out_path = _REPORTS / f"report-{args.version}-{stamp}.json"
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print_scoreboard(report)
    print(f"\nReport written: {out_path.relative_to(_PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
