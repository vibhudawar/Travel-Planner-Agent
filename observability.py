"""Observability: LangSmith tracing toggle + token/cost accounting (WIN 8).

Two layers, mirroring the RAG project:
1. LangSmith tracing behind an env flag — near-no-op when off. Because WIN 1
   moved config to pydantic-settings (no load_dotenv), the LANGSMITH_* values in
   .env don't reach LangChain on their own; configure_tracing() pushes them into
   os.environ when enabled so traces actually flow.
2. Per-run token/cost accounting via LangChain's usage-metadata callback and a
   price table — this is what fills the "$/itinerary" column and gives WIN 8.5 a
   cost baseline to move.
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager

from settings import get_settings

logger = logging.getLogger(__name__)

# USD per 1M tokens. Keep in sync with provider pricing; unknown models cost 0
# (surfaced as such rather than guessed).
PRICES = {
    "gpt-5.4-nano": {"input": 0.20, "output": 1.25},  # the app's default model
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}
_DEFAULT_PRICE = {"input": 0.0, "output": 0.0}


def _price_for(model: str) -> dict:
    if model in PRICES:
        return PRICES[model]
    # Providers report dated variants (e.g. gpt-4o-2024-08-06). Match the LONGEST
    # prefix so "gpt-4o-mini-..." resolves to gpt-4o-mini, not gpt-4o.
    for key in sorted(PRICES, key=len, reverse=True):
        if model.startswith(key):
            return PRICES[key]
    logger.warning("No price for model '%s'; costed at 0.", model)
    return _DEFAULT_PRICE


def configure_tracing() -> bool:
    """Enable LangSmith tracing from settings; return whether it was turned on."""
    settings = get_settings()
    if not settings.langsmith_tracing:
        return False
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key.get_secret_value()
    logger.info("LangSmith tracing enabled (project=%s)", settings.langsmith_project)
    return True


# OpenAI bills cached input tokens at ~50% of the input price (prompt caching).
_CACHE_DISCOUNT = 0.5


def compute_cost(usage_metadata: dict) -> dict:
    """Turn LangChain usage_metadata into cost, crediting cached (prompt-cache) input.

    usage_metadata: {model: {input_tokens, output_tokens, input_token_details: {cache_read}}}
    """
    by_model = {}
    total = 0.0
    total_cached = 0
    for model, usage in (usage_metadata or {}).items():
        price = _price_for(model)
        inp = usage.get("input_tokens", 0) or 0
        out = usage.get("output_tokens", 0) or 0
        cached = (usage.get("input_token_details") or {}).get("cache_read", 0) or 0
        cached = min(cached, inp)
        uncached_in = inp - cached
        cost = (
            uncached_in / 1e6 * price["input"]
            + cached / 1e6 * price["input"] * _CACHE_DISCOUNT
            + out / 1e6 * price["output"]
        )
        by_model[model] = {
            "input_tokens": inp, "cached_input_tokens": cached, "output_tokens": out,
            "cost_usd": round(cost, 6),
        }
        total += cost
        total_cached += cached
    return {
        "total_usd": round(total, 6),
        "input_tokens": sum(m["input_tokens"] for m in by_model.values()),
        "cached_input_tokens": total_cached,
        "output_tokens": sum(m["output_tokens"] for m in by_model.values()),
        "by_model": by_model,
    }


@contextmanager
def track_usage():
    """Aggregate token usage across all LLM calls in the block.

    Usage:
        with track_usage() as cb:
            app.invoke(...)
        cost = compute_cost(cb.usage_metadata)
    """
    from langchain_core.callbacks import get_usage_metadata_callback

    with get_usage_metadata_callback() as cb:
        yield cb
