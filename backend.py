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
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from compute import compute_budget
from enrich import attach_links
from observability import configure_tracing
from prompts import TRIP_PLANNER_SYSTEM_PROMPT, TRIP_SYNTHESIS_PROMPT
from schema import Budget, BudgetItem, ItineraryDraft, WeatherDay, finalize_itinerary
from settings import get_settings
from tools import ALL_TOOLS
from verifier import verify_itinerary


def _budget_payload(computed: dict) -> dict:
    """Public budget fields (currency display + adherence) from a ComputedBudget."""
    return {
        "currency": computed["currency"],
        "items": computed["items"],
        "total": computed["total"],
        "cap": computed["cap"],
        "cap_currency": computed["cap_currency"],
        "home_currency": computed["home_currency"],
        "total_home": computed["total_home"],
        "cap_home": computed["cap_home"],
        "fx_rate": computed["fx_rate"],
        "fx_note": computed["fx_note"],
        "over_budget": computed["over_budget"],
        "over_by_home": computed["over_by_home"],
        "assessment": computed["assessment"],
    }

logger = logging.getLogger(__name__)


class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    # Structured, source-bound itinerary produced by the synthesize node once the
    # trip data has been gathered. None during the conversational/clarifying phase.
    itinerary: Optional[dict]


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
def _get_structurer():
    """LLM bound to structured itinerary output (no tools), on the cheaper
    synthesis model (WIN 8.5 tiering). Built once."""
    settings = get_settings()
    logger.info("Synthesis model=%s", settings.effective_synthesis_model)
    llm = ChatOpenAI(
        model=settings.effective_synthesis_model,
        temperature=settings.temperature,
        max_tokens=settings.synthesis_max_tokens,  # higher: structured JSON can be long
        timeout=settings.request_timeout,
        max_retries=settings.max_retries,
        api_key=settings.openai_api_key.get_secret_value(),
    )
    return llm.with_structured_output(ItineraryDraft)


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


def _extract_weather_meta(messages) -> tuple:
    """Pull (is_forecast, label, days) from the search_weather tool result, if any."""
    import ast
    import json as _json

    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and getattr(msg, "name", None) == "search_weather":
            content = msg.content
            data = content if isinstance(content, dict) else None
            if data is None:
                for parser in (_json.loads, ast.literal_eval):
                    try:
                        data = parser(content)
                        break
                    except Exception:  # noqa: BLE001 - best-effort parse
                        continue
            if isinstance(data, dict):
                return data.get("is_forecast"), data.get("label"), data.get("days") or []
    return None, None, []


def _fmt_weather_day(d: dict) -> str:
    """One concise per-day line from the tool's structured data, e.g.
    '2026-10-30: 26–34°C, light drizzle'. The forecast/seasonal caveat is carried
    once in the label, never repeated into every day's summary."""
    bits = []
    lo, hi = d.get("low_c"), d.get("high_c")
    if lo is not None and hi is not None:
        bits.append(f"{round(lo)}–{round(hi)}°C")
    if d.get("conditions"):
        bits.append(d["conditions"])
    body = ", ".join(bits)
    date = d.get("date") or ""
    return f"{date}: {body}" if body else str(date)


def _synthesize_node(state: ChatState) -> dict:
    """Turn the gathered conversation into a structured, source-bound itinerary.

    Degrades gracefully: if structured synthesis fails, the free-text answer from
    chat_node still stands and ``itinerary`` is left unset.
    """
    messages = state["messages"]
    called_tools = [m.name for m in messages if isinstance(m, ToolMessage) and getattr(m, "name", None)]
    try:
        draft: ItineraryDraft = _get_structurer().invoke(
            [SystemMessage(content=TRIP_SYNTHESIS_PROMPT)] + messages
        )
        itinerary = finalize_itinerary(draft, called_tools)
        # Code-authored currency: the flight/hotel tools always request USD, so the
        # price currency is USD regardless of what the model guessed (it sometimes
        # mislabels prices "INR" when the user's budget is in rupees, which wrecks
        # the budget math). Stamp it rather than trust the LLM.
        for f in itinerary.flights:
            f.currency = "USD"
        for h in itinerary.hotels:
            h.currency = "USD"
        # Code-authored weather (WIN 5): build clean per-day lines from the tool's
        # structured data so a trip months out never shows a "forecast", and the
        # seasonal caveat isn't duplicated into every day's summary by the LLM.
        is_forecast, weather_label, weather_days = _extract_weather_meta(messages)
        if weather_days:
            itinerary.weather = [
                WeatherDay(
                    date=d.get("date"),
                    summary=_fmt_weather_day(d),
                    is_forecast=is_forecast,
                    label=weather_label,
                )
                for d in weather_days
            ]
        elif weather_label is not None:
            for w in itinerary.weather:
                if w.is_forecast is None:
                    w.is_forecast = is_forecast
                if not w.label:
                    w.label = weather_label
        # Deterministic budget: overwrite the model's proposed budget with one
        # computed in code from the source-bound facts + real dates (WIN 4), so
        # the total always adds up and is grounded rather than LLM-guessed.
        computed = compute_budget(
            itinerary.model_dump(mode="python"),
            itinerary.travelers,
            budget_cap=itinerary.budget_cap,
            budget_currency=itinerary.budget_currency,
        )
        payload = _budget_payload(computed)
        itinerary.budget = Budget(
            **{**payload, "items": [BudgetItem(**item) for item in computed["items"]]}
        )
        if computed["mixed_currency"]:
            logger.warning("Itinerary has facts in an unrecognized currency; budget may be incomplete.")
        return {"itinerary": itinerary.model_dump(mode="json")}
    except Exception as exc:  # noqa: BLE001 - never crash the chat on synthesis failure
        logger.warning("Itinerary synthesis failed: %s: %s", type(exc).__name__, exc)
        return {"itinerary": None}


def _verify_node(state: ChatState) -> dict:
    """Value-verify the itinerary: prune unsupported facts, recompute budget, flag.

    The trust lever (WIN 7): a fabricated price/name can't survive to the user,
    and a removed category becomes honest abstention. Recomputes the budget on the
    pruned facts so the total stays consistent.
    """
    itinerary = state.get("itinerary")
    if not itinerary:
        return {}
    try:
        pruned, report = verify_itinerary(itinerary, state["messages"])
        # Attach actionable links to the facts that survived verification.
        pruned = attach_links(pruned, state["messages"])
        # Defensive: prices come from USD-denominated tool calls (see synthesize).
        for f in pruned.get("flights", []):
            f["currency"] = "USD"
        for h in pruned.get("hotels", []):
            h["currency"] = "USD"
        computed = compute_budget(
            pruned,
            pruned.get("travelers"),
            budget_cap=pruned.get("budget_cap"),
            budget_currency=pruned.get("budget_currency"),
        )
        pruned["budget"] = _budget_payload(computed)
        pruned["verification"] = report
        if report["n_removed"]:
            logger.warning("Verifier removed %d unsupported fact(s): %s", report["n_removed"], report["removed"])
        return {"itinerary": pruned}
    except Exception as exc:  # noqa: BLE001 - verification must not break the chat
        logger.warning("Verification failed: %s: %s", type(exc).__name__, exc)
        return {}


def _route_after_chat(state: ChatState) -> str:
    """Route the ReAct loop.

    - pending tool calls -> run the tools
    - no tool calls but tools were already used -> synthesize the itinerary
    - no tool calls and no tools used yet -> a clarifying question; end the turn
    """
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    if any(isinstance(m, ToolMessage) for m in state["messages"]):
        return "synthesize"
    return END


def build_graph(checkpointer: SqliteSaver | None = None):
    """Build and compile the agent graph.

    Pass ``checkpointer`` to inject a fake in tests; defaults to the shared
    SQLite checkpointer.
    """
    if checkpointer is None:
        checkpointer = get_checkpointer()

    configure_tracing()  # enable LangSmith tracing if configured (near-no-op when off)
    llm_with_tools = get_llm().bind_tools(ALL_TOOLS)

    graph = StateGraph(ChatState)
    graph.add_node("chat_node", lambda state: _chat_node(state, llm_with_tools))
    graph.add_node("tools", ToolNode(ALL_TOOLS))
    graph.add_node("synthesize", _synthesize_node)
    graph.add_node("verify", _verify_node)

    graph.add_edge(START, "chat_node")
    graph.add_conditional_edges(
        "chat_node",
        _route_after_chat,
        {"tools": "tools", "synthesize": "synthesize", END: END},
    )
    graph.add_edge("tools", "chat_node")  # loop back after tool execution
    graph.add_edge("synthesize", "verify")  # value-verify before finishing
    graph.add_edge("verify", END)

    return graph.compile(checkpointer=checkpointer)


@lru_cache(maxsize=1)
def get_chatbot():
    """Return the compiled agent, built once, lazily."""
    return build_graph()


def retrieve_all_threads() -> list:
    """List all conversation thread ids recorded by the checkpointer."""
    all_threads = set()
    for checkpoint in get_checkpointer().list(None):
        all_threads.add(checkpoint.config["configurable"]["thread_id"])
    return list(all_threads)
