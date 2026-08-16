"""LangGraph trip-planning agent (WIN 1: no import-time side effects).

Importing this module builds nothing and opens no connections. Construct the app
lazily through the factories: ``get_llm`` / ``build_graph`` / ``get_chatbot`` /
``get_checkpointer``. ``build_graph`` accepts an injected checkpointer so tests
can supply an in-memory fake.
"""
from __future__ import annotations

import logging
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from prompts import TRIP_PLANNER_SYSTEM_PROMPT
from settings import get_settings
from tools import ALL_TOOLS

logger = logging.getLogger(__name__)


# -------------------
# State
# -------------------
class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# -------------------
# Factories
# -------------------
def get_llm() -> ChatOpenAI:
    """Construct the pinned chat model from validated settings."""
    settings = get_settings()
    logger.info(
        "Initializing ChatOpenAI (model=%s, temperature=%s)",
        settings.openai_model,
        settings.temperature,
    )
    return ChatOpenAI(
        model=settings.openai_model,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        timeout=settings.request_timeout,
        max_retries=settings.max_retries,
        api_key=settings.openai_api_key.get_secret_value(),
    )


@lru_cache(maxsize=1)
def get_checkpointer() -> SqliteSaver:
    """Lazily open the SQLite checkpointer connection (opened once, then reused)."""
    settings = get_settings()
    db_path = Path(settings.resolved_sqlite_path())
    db_path.parent.mkdir(parents=True, exist_ok=True)  # ensure the directory exists
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return SqliteSaver(conn=conn)


def _chat_node(state: ChatState, llm_with_tools) -> dict:
    """LLM node that may answer or request a tool call."""
    messages = state["messages"]
    # Prepend the system prompt only if it isn't already the first message.
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=TRIP_PLANNER_SYSTEM_PROMPT)] + messages
    return {"messages": [llm_with_tools.invoke(messages)]}


def build_graph(checkpointer: SqliteSaver | None = None):
    """Build and compile the agent graph.

    Pass ``checkpointer`` to inject a fake in tests; defaults to the shared
    SQLite checkpointer.
    """
    if checkpointer is None:
        checkpointer = get_checkpointer()

    llm_with_tools = get_llm().bind_tools(ALL_TOOLS)

    graph = StateGraph(ChatState)
    graph.add_node("chat_node", lambda state: _chat_node(state, llm_with_tools))
    graph.add_node("tools", ToolNode(ALL_TOOLS))

    graph.add_edge(START, "chat_node")
    graph.add_conditional_edges("chat_node", tools_condition)
    graph.add_edge("tools", "chat_node")  # loop back after tool execution

    return graph.compile(checkpointer=checkpointer)


@lru_cache(maxsize=1)
def get_chatbot():
    """Return the compiled agent, built once, lazily."""
    return build_graph()


# -------------------
# Helper
# -------------------
def retrieve_all_threads() -> list:
    """List all conversation thread ids recorded by the checkpointer."""
    all_threads = set()
    for checkpoint in get_checkpointer().list(None):
        all_threads.add(checkpoint.config["configurable"]["thread_id"])
    return list(all_threads)
