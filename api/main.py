"""FastAPI app for the Trip Planner agent (WIN 9.1).

Lifespan wires the Postgres checkpointer + conversation pool + compiled graph;
routes serve SSE chat and conversation history. Auth is a Supabase Bearer JWT
(no CSRF machinery needed — the browser never sends it cross-origin). Errors
return generic messages; details are logged server-side.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from api import db
from api.auth import get_current_user
from api.schemas import AuthedUser, ChatRequest, NewConversationRequest, ShareRequest
from api.streaming import sse_frame, stream_agent
from backend import build_graph
from settings import get_settings

logger = logging.getLogger(__name__)

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.require_api_settings()  # fail fast if Supabase/DB config is missing
    dsn = settings.checkpointer_dsn
    async with AsyncConnectionPool(dsn, open=False) as pool, AsyncPostgresSaver.from_conn_string(dsn) as saver:
        await pool.open()
        await saver.setup()  # creates checkpointer tables if absent
        app.state.pool = pool
        app.state.graph = build_graph(checkpointer=saver)
        logger.info("API ready (Postgres checkpointer + graph initialized)")
        yield


def get_pool(request: Request) -> AsyncConnectionPool:
    return request.app.state.pool


def get_graph(request: Request):
    return request.app.state.graph


def create_app() -> FastAPI:
    app = FastAPI(title="Trip Planner API", lifespan=lifespan)
    settings = get_settings()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for key, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response

    @app.exception_handler(Exception)
    async def on_unhandled(request: Request, exc: Exception):  # noqa: ARG001
        logger.exception("Unhandled error")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(request: Request):
        if not getattr(request.app.state, "graph", None):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "not ready")
        return {"status": "ready"}

    @app.get("/locations")
    async def locations(q: str = "", limit: int = 8):
        """Airport autocomplete (public reference data). Returns ranked candidates."""
        from locations import search_locations

        return {"results": search_locations(q, limit=max(1, min(limit, 20)))}

    @app.post("/share")
    async def share_itinerary(
        body: ShareRequest,
        user: AuthedUser = Depends(get_current_user),
        pool: AsyncConnectionPool = Depends(get_pool),
    ):
        """Freeze an itinerary as a public snapshot; returns its short code."""
        itinerary = body.itinerary
        if not itinerary.get("destination"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "itinerary has no destination")
        short_code = await db.create_shared_itinerary(
            pool, user.id, itinerary.get("destination"), itinerary
        )
        return {"short_code": short_code}

    @app.get("/shared/{short_code}")
    async def get_shared(short_code: str, pool: AsyncConnectionPool = Depends(get_pool)):
        """Public, read-only snapshot by short code (no auth, no user data)."""
        snapshot = await db.get_shared_itinerary(pool, short_code)
        if not snapshot:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "shared itinerary not found")
        return snapshot

    @app.post("/conversations")
    async def create_conversation(
        body: NewConversationRequest,
        user: AuthedUser = Depends(get_current_user),
        pool: AsyncConnectionPool = Depends(get_pool),
    ):
        conv_id = await db.create_conversation(pool, user.id, body.title)
        return {"id": conv_id, "title": body.title}

    @app.get("/conversations")
    async def list_conversations(
        user: AuthedUser = Depends(get_current_user),
        pool: AsyncConnectionPool = Depends(get_pool),
    ):
        return {"conversations": await db.list_conversations(pool, user.id)}

    @app.get("/conversations/{conversation_id}")
    async def get_conversation(
        conversation_id: str,
        user: AuthedUser = Depends(get_current_user),
        pool: AsyncConnectionPool = Depends(get_pool),
        graph=Depends(get_graph),
    ):
        owner = await db.conversation_owner(pool, conversation_id)
        if owner != user.id:  # 404 (not 403) so we don't leak existence
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
        state = await graph.aget_state({"configurable": {"thread_id": conversation_id}})
        messages = []
        for msg in state.values.get("messages", []):
            if isinstance(msg, HumanMessage):
                messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage) and not msg.tool_calls and msg.content:
                messages.append({"role": "assistant", "content": msg.content})
        return {"messages": messages, "itinerary": state.values.get("itinerary")}

    @app.post("/chat/stream")
    async def chat_stream(
        body: ChatRequest,
        user: AuthedUser = Depends(get_current_user),
        pool: AsyncConnectionPool = Depends(get_pool),
        graph=Depends(get_graph),
    ):
        is_new = body.conversation_id is None
        if is_new:
            thread_id = await db.create_conversation(pool, user.id, body.message[:60])
        else:
            thread_id = body.conversation_id
            if await db.conversation_owner(pool, thread_id) != user.id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

        async def event_stream():
            if is_new:
                yield sse_frame("conversation", {"conversation_id": thread_id})
            async for frame in stream_agent(graph, thread_id, body.message):
                yield frame
            await db.touch_conversation(pool, thread_id, body.message[:60])

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
