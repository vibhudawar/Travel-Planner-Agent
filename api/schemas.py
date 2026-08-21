"""Request/response models for the API (WIN 9.1)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: Optional[str] = None  # None => start a new conversation


class NewConversationRequest(BaseModel):
    title: Optional[str] = None


class ShareRequest(BaseModel):
    # The frozen itinerary snapshot to publish. Kept as a permissive dict (the
    # itinerary was already produced/verified by the graph) with a size guard via
    # the destination check in the route; we don't re-run full schema validation
    # so a valid card is never rejected on a datetime/format technicality.
    itinerary: dict


class ConversationSummary(BaseModel):
    id: str
    title: Optional[str]
    updated_at: str


class AuthedUser(BaseModel):
    id: str
    email: Optional[str] = None
