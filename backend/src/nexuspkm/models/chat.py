"""Chat session and message models.

Defines the data contracts for the chat interface: ChatMessage with
role-constrained Literal type, source attributions linking back to
documents, and ChatSession grouping messages into a conversation.

Spec: F-005 FR-3, FR-4
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from nexuspkm.models.document import SourceAttribution


class ChatMessage(BaseModel):
    id: str = Field(min_length=1)
    role: Literal["user", "assistant"]
    content: str
    sources: list[SourceAttribution] = Field(default_factory=list)
    timestamp: AwareDatetime


class ChatSession(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: AwareDatetime
    updated_at: AwareDatetime
