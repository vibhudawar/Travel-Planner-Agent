"""Slot-aware semantic response cache (WIN 9.2) on Supabase pgvector.

The correctness gate is the **canonical slot key** — an exact match on
`destination | date-range | travelers | budget_band`. Only among slot-equal
candidates does the **embedding** of the soft intent ("relaxing" / "foodie") rank
the best match. This kills the "served a $2000 plan for a $5000 request" failure
class (different budget_band ⇒ different key ⇒ never matched).

This module is the pure cache layer: slot extraction, the key, embeddings, and the
pgvector lookup/store. Orchestration (refresh volatile prices on a hit, reassemble,
persist) lives in backend.py. Everything here fails safe — any error is a miss.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from psycopg.types.json import Json
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field

from settings import get_settings

logger = logging.getLogger(__name__)

# Budget bands in USD, edges ~1.5–2x apart so similar budgets group but very
# different ones don't (the reliability point of the slot key).
_BUDGET_BANDS_USD = [
    (0, 500), (500, 1000), (1000, 1750), (1750, 3000),
    (3000, 5000), (5000, 8000), (8000, 10**9),
]

# The stable itinerary fields worth caching; volatile facts (flights/hotels/budget)
# are intentionally excluded — they are re-fetched/recomputed on every hit.
SKELETON_FIELDS = (
    "destination", "origin", "start_date", "end_date", "travelers",
    "budget_cap", "budget_currency", "overview", "attractions", "weather", "days", "tips",
)


def budget_band(cap_usd: Optional[float]) -> str:
    if not cap_usd or cap_usd <= 0:
        return "none"
    for lo, hi in _BUDGET_BANDS_USD:
        if lo <= cap_usd < hi:
            return f"{lo}-{hi}"
    return "none"


def _norm(value) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(value or "").lower())).strip()


class SlotExtraction(BaseModel):
    is_plan: bool = Field(description="True ONLY if this is a concrete trip-planning request that names a destination")
    destination: Optional[str] = None
    origin: Optional[str] = None
    start_date: Optional[str] = Field(default=None, description="YYYY-MM-DD if present")
    end_date: Optional[str] = Field(default=None, description="YYYY-MM-DD if present")
    travelers: Optional[int] = None
    budget_cap: Optional[float] = Field(default=None, description="Numeric budget if stated")
    budget_currency: Optional[str] = Field(default=None, description="ISO code of the budget, e.g. INR/USD")
    intent: Optional[str] = Field(default=None, description="Short phrase of soft preferences, e.g. 'relaxing beach', 'foodie', 'budget backpacking'")


_SLOT_PROMPT = (
    "Extract trip-planning slots from the user's message. Set is_plan=true ONLY if the "
    "message names a destination and is a real planning request (not a greeting or a "
    "follow-up question). Use YYYY-MM-DD for dates. 'intent' is a short phrase capturing "
    "soft preferences (vibe/style), not the destination or dates."
)


@lru_cache(maxsize=1)
def _slot_llm():
    s = get_settings()
    return ChatOpenAI(
        model=s.openai_model, temperature=0,
        api_key=s.openai_api_key.get_secret_value(),
        timeout=s.request_timeout, max_retries=1,
    ).with_structured_output(SlotExtraction)


def extract_slots(message: str) -> Optional[dict]:
    """Nano slot extraction from the raw message. None on any failure."""
    try:
        result: SlotExtraction = _slot_llm().invoke(
            [SystemMessage(content=_SLOT_PROMPT), HumanMessage(content=message)]
        )
        return result.model_dump()
    except Exception as exc:  # noqa: BLE001 - cache is best-effort
        logger.warning("Slot extraction failed: %s", exc)
        return None


@lru_cache(maxsize=1)
def _embedder():
    s = get_settings()
    return OpenAIEmbeddings(model=s.embedding_model, api_key=s.openai_api_key.get_secret_value())


def embed(text: str) -> List[float]:
    return _embedder().embed_query(text or "")


def canonical_slot_key(slots: dict) -> Optional[str]:
    """Hard cache key from the canonical slots. None if the request isn't cacheable
    (no destination or no derivable date range)."""
    from compute import normalize_currency, to_usd, trip_nights
    from locations import resolve_iata

    # Canonicalize the destination to its primary airport code so "Hanoi",
    # "Hanoi, Vietnam", and "HAN" all key identically (and homonym cities like
    # Paris/Paris,TX resolve apart); fall back to the normalized city name.
    dest_raw = slots.get("destination")
    dest = (resolve_iata(dest_raw) if dest_raw else None) or _norm(str(dest_raw or "").split(",")[0])
    start, end = slots.get("start_date"), slots.get("end_date")
    nights = trip_nights(start, end)
    if not dest or not start or not nights:
        return None
    travelers = slots.get("travelers") or 2
    cap = slots.get("budget_cap")
    ccy = normalize_currency(slots.get("budget_currency")) or "USD"
    cap_usd = to_usd(cap, ccy) if cap else None
    return f"{dest}|{start}|{nights}n|{travelers}p|{budget_band(cap_usd)}"


def _vec_literal(vec: List[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


async def lookup(
    pool: AsyncConnectionPool, slot_key: str, embedding: List[float], threshold: float, ttl_hours: float
) -> Optional[dict]:
    """Best slot-equal, within-TTL skeleton whose intent is within `threshold` cosine
    distance; bumps hit_count. None on miss/error."""
    query = (
        "SELECT id, response_skeleton, intent_embedding <=> %s::vector AS dist "
        "FROM query_cache "
        "WHERE slot_key = %s AND created_at > now() - (%s * interval '1 hour') "
        "ORDER BY dist ASC LIMIT 1"
    )
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(query, (_vec_literal(embedding), slot_key, ttl_hours))
            row = await cur.fetchone()
            if not row:
                return None
            cache_id, skeleton, dist = row
            if dist is None or float(dist) > threshold:
                return None
            await conn.execute("UPDATE query_cache SET hit_count = hit_count + 1 WHERE id = %s", (cache_id,))
            return skeleton
    except Exception as exc:  # noqa: BLE001 - a miss is always safe
        logger.warning("Cache lookup failed: %s", exc)
        return None


async def store(
    pool: AsyncConnectionPool,
    slot_key: str,
    intent: Optional[str],
    embedding: List[float],
    skeleton: dict,
    ttl_hours: float,
) -> None:
    try:
        async with pool.connection() as conn:
            await conn.execute(
                "INSERT INTO query_cache (slot_key, intent, intent_embedding, response_skeleton, ttl_hours) "
                "VALUES (%s, %s, %s::vector, %s, %s)",
                (slot_key, intent, _vec_literal(embedding), Json(skeleton), ttl_hours),
            )
    except Exception as exc:  # noqa: BLE001 - failing to cache must never break a turn
        logger.warning("Cache store failed: %s", exc)
