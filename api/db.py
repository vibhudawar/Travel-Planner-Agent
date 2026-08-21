"""Conversation persistence (WIN 9.1).

A `conversations` table maps users to LangGraph thread ids (the checkpointer holds
the message state). All queries are parameterized and scoped by ``user_id`` — the
app enforces ownership even though the pool connects with the service role
(RLS on the table is the defense-in-depth layer; see supabase/migrations).
"""
from __future__ import annotations

import secrets
import uuid
from typing import Optional

from psycopg.types.json import Json
from psycopg_pool import AsyncConnectionPool

from api.schemas import ConversationSummary


async def create_conversation(pool: AsyncConnectionPool, user_id: str, title: Optional[str]) -> str:
    conv_id = str(uuid.uuid4())
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO conversations (id, user_id, title) VALUES (%s, %s, %s)",
            (conv_id, user_id, title),
        )
    return conv_id


async def list_conversations(pool: AsyncConnectionPool, user_id: str) -> list[ConversationSummary]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id, title, updated_at FROM conversations "
            "WHERE user_id = %s ORDER BY updated_at DESC LIMIT 100",
            (user_id,),
        )
        rows = await cur.fetchall()
    return [
        ConversationSummary(id=str(r[0]), title=r[1], updated_at=r[2].isoformat()) for r in rows
    ]


async def conversation_owner(pool: AsyncConnectionPool, conv_id: str) -> Optional[str]:
    """Return the owner's user_id for a conversation, or None if it doesn't exist."""
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT user_id FROM conversations WHERE id = %s", (conv_id,))
        row = await cur.fetchone()
    return str(row[0]) if row else None


async def touch_conversation(
    pool: AsyncConnectionPool, conv_id: str, title: Optional[str] = None
) -> None:
    """Bump updated_at; set the title only if it is currently null."""
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE conversations SET updated_at = now(), "
            "title = COALESCE(title, %s) WHERE id = %s",
            (title, conv_id),
        )


async def create_shared_itinerary(
    pool: AsyncConnectionPool, user_id: str, destination: Optional[str], itinerary: dict
) -> str:
    """Freeze an itinerary under a new unguessable short code and return the code."""
    async with pool.connection() as conn:
        for _ in range(5):  # retry on the (astronomically unlikely) code collision
            short_code = secrets.token_urlsafe(8)
            try:
                await conn.execute(
                    "INSERT INTO shared_itineraries (short_code, user_id, destination, itinerary) "
                    "VALUES (%s, %s, %s, %s)",
                    (short_code, user_id, destination, Json(itinerary)),
                )
                return short_code
            except Exception:
                await conn.rollback()
        raise RuntimeError("Could not allocate a unique share code")


async def get_shared_itinerary(pool: AsyncConnectionPool, short_code: str) -> Optional[dict]:
    """Return a public snapshot {itinerary, destination, created_at} or None. No user_id."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT itinerary, destination, created_at FROM shared_itineraries WHERE short_code = %s",
            (short_code,),
        )
        row = await cur.fetchone()
    if not row:
        return None
    return {"itinerary": row[0], "destination": row[1], "created_at": row[2].isoformat()}
