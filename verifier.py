"""Value-level groundedness verifier + abstention (plan-v2.md WIN 7).

WIN 3/4 groundedness is attribution + name-level. This is the trust lever: a
verification pass that checks every source-bound fact's *concrete values* (price,
name, rating) against the actual tool outputs, then **removes** anything it can't
support so a fabricated price can never reach the user. Facts removed because a
tool errored/returned nothing become honest abstention ("flights could not be
verified and were omitted").

Two layers, "don't trust, verify":
1. Deterministic value check (authoritative, free, ungameable) — prunes facts.
2. An optional second-model pass (judge_model != generator) that reviews the
   pruned itinerary holistically and adds advisory notes (Constitutional-AI /
   verifier-model style). Never fabricates facts; only flags.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import List, Optional, Tuple

from langchain_core.messages import ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from settings import get_settings

# Generic tokens that don't distinguish one fact from another (mirrors the eval
# metric's list, kept local so production code doesn't depend on evals/).
_GENERIC_TOKENS = {
    "hotel", "hotels", "airline", "airlines", "temple", "shrine", "museum", "park",
    "inn", "resort", "tokyo", "japan", "paris", "london", "kyoto", "the", "and",
}


def _content_to_str(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(b.get("text", b)) if isinstance(b, dict) else str(b) for b in content)
    return str(content)


def _tool_content_index(messages) -> dict:
    idx: dict = {}
    for msg in messages:
        if isinstance(msg, ToolMessage) and getattr(msg, "name", None):
            idx[msg.name] = idx.get(msg.name, "") + " " + _content_to_str(msg.content)
    return idx


def _value_supported(value: str, content: str) -> bool:
    """Whole value present, or a distinctive token of it (tolerates normalization)."""
    v = (value or "").strip().lower()
    if v == "":
        return True
    if v in content:
        return True
    tokens = [t for t in re.split(r"[^a-z0-9]+", v) if len(t) >= 4 and t not in _GENERIC_TOKENS]
    return any(t in content for t in tokens)


def _number_supported(num, content: str) -> bool:
    """A numeric value (e.g. a price) appears in the tool result."""
    if num is None:
        return True  # nothing to check
    try:
        n = float(num)
    except (TypeError, ValueError):
        return True
    candidates = {str(int(n)), f"{n:g}", f"{n:.2f}"}
    return any(c in content for c in candidates)


class _LLMIssues(BaseModel):
    issues: List[str] = Field(default_factory=list, description="Facts not supported by the tool outputs")


@lru_cache(maxsize=1)
def _llm_verifier():
    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.judge_model,
        temperature=0,
        timeout=settings.request_timeout,
        max_retries=settings.max_retries,
        api_key=settings.openai_api_key.get_secret_value(),
    )
    return llm.with_structured_output(_LLMIssues)


_LLM_VERIFY_PROMPT = """You are a strict fact-checker for a travel itinerary.

Flag a fact ONLY if a concrete value — a price, a name, or a date/time — is clearly
absent from and cannot be derived from the TOOL OUTPUTS, i.e. it looks fabricated.

Do NOT flag any of the following (these are fine):
- capitalization, spacing, or formatting differences
- field naming differences (e.g. "price" vs "price_per_night")
- missing optional fields (booking links, thumbnails)
- currency labels, rounding, or unit wording
- reworded or summarized prose

If every price and name in the FACTS matches the TOOL OUTPUTS, return an empty list.

TOOL OUTPUTS:
{tool_outputs}

FACTS:
{facts}"""


def _llm_notes(itinerary: dict, content_index: dict) -> List[str]:
    facts = {k: itinerary.get(k, []) for k in ("flights", "hotels", "attractions", "weather")}
    try:
        result: _LLMIssues = _llm_verifier().invoke(
            _LLM_VERIFY_PROMPT.format(
                tool_outputs=str(content_index)[:6000],
                facts=str(facts)[:4000],
            )
        )
        return list(result.issues)
    except Exception:  # noqa: BLE001 - advisory only; never break the pipeline
        return []


def verify_itinerary(itinerary: dict, messages, use_llm: Optional[bool] = None) -> Tuple[dict, dict]:
    """Return (pruned_itinerary, verification_report).

    Removes source-bound facts whose values aren't supported by the tool outputs;
    records what was removed and why, and any abstention disclaimers.
    """
    settings = get_settings()
    if use_llm is None:
        use_llm = settings.enable_llm_verifier

    content_index = {k: v.lower() for k, v in _tool_content_index(messages).items()}
    pruned = dict(itinerary)
    removed: List[dict] = []
    n_checked = 0

    def check(items, kind, identity_key, price_key=None):
        nonlocal n_checked
        kept = []
        for it in items or []:
            n_checked += 1
            src = it.get("source_tool")
            content = content_index.get(src, "")
            name_ok = _value_supported(str(it.get(identity_key) or ""), content)
            price_ok = _number_supported(it.get(price_key), content) if price_key else True
            if src in content_index and name_ok and price_ok:
                kept.append(it)
            else:
                reason = (
                    "source tool not called/errored" if src not in content_index
                    else "name not in tool result" if not name_ok
                    else "price not in tool result"
                )
                removed.append({"kind": kind, "identity": it.get(identity_key), "source_tool": src, "reason": reason})
        return kept

    pruned["flights"] = check(itinerary.get("flights"), "flight", "airline", "price")
    pruned["hotels"] = check(itinerary.get("hotels"), "hotel", "name", "price_per_night")
    pruned["attractions"] = check(itinerary.get("attractions"), "attraction", "name")
    pruned["weather"] = check(itinerary.get("weather"), "weather", "summary")

    disclaimers = []
    for kind in ("flight", "hotel", "attraction", "weather"):
        if any(r["kind"] == kind for r in removed):
            disclaimers.append(f"Some {kind} details could not be verified against live data and were omitted.")

    report = {
        "status": "flagged" if removed else "verified",
        "n_facts_checked": n_checked,
        "n_removed": len(removed),
        "removed": removed,
        "disclaimers": disclaimers,
        "verifier_model": settings.judge_model,
        "llm_notes": _llm_notes(pruned, content_index) if use_llm else [],
    }
    return pruned, report
