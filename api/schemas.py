"""Request/response models for the API (WIN 9.1)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: Optional[str] = None  # None => start a new conversation


class NewConversationRequest(BaseModel):
    title: Optional[str] = None


class ConversationSummary(BaseModel):
    id: str
    title: Optional[str]
    updated_at: str


class AuthedUser(BaseModel):
    id: str
    email: Optional[str] = None
