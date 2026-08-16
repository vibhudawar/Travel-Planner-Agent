"""Structured, source-bound itinerary schema (plan-v2.md WIN 3).

Every atomic fact in an itinerary — a flight, a hotel, an activity, a weather day
— is a typed object that MUST declare which tool it came from (``source_tool``).
This makes hallucination structural rather than prompt-discouraged: the model
cannot emit a price or hotel without attributing it to a tool. Free-text advice
lives in ``tips``, kept separate from source-bound facts.

The LLM produces an ``ItineraryDraft`` (facts + prose). Code then wraps it into a
final ``Itinerary`` with ``provenance`` built from the tools that were *actually*
called (see ``finalize_itinerary``) — provenance is never model-authored, so it
can't be faked. The WIN 2 groundedness metric scores each fact against the real
tool results; WIN 4 will compute/verify the budget; WIN 7 will value-verify.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class SourceTool(str, Enum):
    """The tools a fact may be attributed to (mirrors tools.ALL_TOOLS)."""

    flights = "search_flights"
    hotels = "search_hotels"
    weather = "search_weather"
    attractions = "search_attractions"
    youtube = "search_youtube_vlogs"
    websearch = "google_search"


class FlightOption(BaseModel):
    airline: str
    price: Optional[float] = None
    currency: str = "USD"
    depart_time: Optional[str] = None
    arrive_time: Optional[str] = None
    stops: Optional[int] = None
    booking_link: Optional[str] = None
    source_tool: SourceTool = SourceTool.flights


class HotelOption(BaseModel):
    name: str
    price_per_night: Optional[float] = None
    currency: str = "USD"
    rating: Optional[float] = None
    link: Optional[str] = None
    source_tool: SourceTool = SourceTool.hotels


class Activity(BaseModel):
    name: str
    kind: Optional[str] = Field(default=None, description="e.g. sightseeing, food, museum")
    notes: Optional[str] = None
    source_tool: SourceTool = SourceTool.attractions


class WeatherDay(BaseModel):
    date: Optional[str] = None
    summary: str
    # Set in code from the weather tool result (WIN 5) — never present seasonal
    # averages as a live forecast.
    is_forecast: Optional[bool] = None
    label: Optional[str] = None
    source_tool: SourceTool = SourceTool.weather


class DayPlan(BaseModel):
    day: int
    date: Optional[str] = None
    title: Optional[str] = None
    # Free-text scheduling steps (e.g. "Morning: Senso-ji Temple", "Lunch in
    # Asakusa", "Free time"). This is itinerary *arrangement* / prose — it may
    # reference source-bound attractions but is NOT itself a source-bound fact,
    # so it is not scored for groundedness. The tool-sourced attractions live in
    # the top-level ``attractions`` list.
    activities: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class BudgetItem(BaseModel):
    label: str
    amount: float
    source_tool: Optional[SourceTool] = None


class Budget(BaseModel):
    currency: str = "USD"
    items: List[BudgetItem] = Field(default_factory=list)
    # total is proposed by the model here; WIN 4 will compute and verify it in code.
    total: Optional[float] = None


class Source(BaseModel):
    """One provenance entry — built from a tool that actually ran, not by the LLM."""

    tool: SourceTool
    retrieved_at: datetime
    summary: Optional[str] = None


class ItineraryDraft(BaseModel):
    """The structured itinerary the LLM emits (facts must come from tool results)."""

    destination: str
    origin: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    travelers: Optional[int] = None
    overview: Optional[str] = None
    flights: List[FlightOption] = Field(default_factory=list)
    hotels: List[HotelOption] = Field(default_factory=list)
    weather: List[WeatherDay] = Field(default_factory=list)
    # Tool-sourced attractions (exact names from search_attractions) — source-bound
    # facts, kept separate from the day-by-day prose in ``days``.
    attractions: List[Activity] = Field(default_factory=list)
    days: List[DayPlan] = Field(default_factory=list)
    budget: Budget = Field(default_factory=Budget)
    tips: List[str] = Field(default_factory=list)  # free-text prose, NOT source-bound


class Itinerary(ItineraryDraft):
    """A finalized itinerary: the draft plus code-authored provenance."""

    provenance: List[Source] = Field(default_factory=list)
    generated_at: Optional[datetime] = None
    # WIN 7 verification report (facts removed, disclaimers, verifier notes).
    verification: Optional[dict] = None


def finalize_itinerary(draft: ItineraryDraft, called_tools: List[str]) -> Itinerary:
    """Wrap an LLM draft into a final Itinerary with code-authored provenance.

    ``provenance`` is derived from the tools that actually ran (deduplicated,
    order-preserving), each stamped with the current time. This is the trusted
    record of what was really retrieved; the groundedness metric checks each
    fact's ``source_tool`` against it and against the real tool results.
    """
    now = datetime.now(timezone.utc)
    seen: set[str] = set()
    provenance: List[Source] = []
    for name in called_tools:
        if name in seen:
            continue
        try:
            tool = SourceTool(name)
        except ValueError:
            continue  # not a fact-producing tool
        seen.add(name)
        provenance.append(Source(tool=tool, retrieved_at=now))
    return Itinerary(**draft.model_dump(), provenance=provenance, generated_at=now)
