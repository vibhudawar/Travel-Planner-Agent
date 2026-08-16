"""SSE streaming of the agent turn (WIN 9.1).

Runs the LangGraph agent with ``astream`` and emits typed SSE frames the frontend
consumes: `token` (assistant prose), `tool` (which tools ran), `itinerary` (the
final structured, verified itinerary), `done`, `error`. Frame format matches the
frontend parser (blocks separated by a blank line, `event:` + `data:` lines).
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Optional

from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

_RECURSION_LIMIT = 18


def sse_frame(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def stream_agent(graph, thread_id: str, message: str) -> AsyncIterator[str]:
    """Yield SSE frames for one agent turn on ``thread_id``."""
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": _RECURSION_LIMIT}
    itinerary: Optional[dict] = None
    try:
        async for mode, chunk in graph.astream(
            {"messages": [HumanMessage(content=message)]},
            config=config,
            stream_mode=["messages", "updates"],
        ):
            if mode == "messages":
                msg, meta = chunk
                # Stream only the conversational answer (chat_node), not the
                # structured-synthesis or verifier model's internal tokens.
                if meta.get("langgraph_node") == "chat_node":
                    text = getattr(msg, "content", "")
                    if isinstance(text, str) and text:
                        yield sse_frame("token", text)
            elif mode == "updates":
                for node, update in (chunk or {}).items():
                    if node == "tools" and update:
                        names = sorted(
                            {getattr(m, "name", "") for m in update.get("messages", []) if getattr(m, "name", None)}
                        )
                        if names:
                            yield sse_frame("tool", names)
                    elif node in ("synthesize", "verify") and update and update.get("itinerary"):
                        itinerary = update["itinerary"]  # verify's copy supersedes synthesize's

        if itinerary is not None:
            yield sse_frame("itinerary", itinerary)
        yield sse_frame("done", {"thread_id": thread_id})
    except Exception:  # noqa: BLE001 - generic message to client; details logged
        logger.exception("Agent stream failed for thread %s", thread_id)
        yield sse_frame("error", "The assistant hit an error. Please try again.")
