"""Chat session and message models.

Defines the data contracts for the chat interface: ChatMessage with
role-constrained Literal type, source attributions linking back to
documents, and ChatSession grouping messages into a conversation.

Spec: F-005 FR-3, FR-4
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from nexuspkm.models.document import SourceAttribution


class ChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    sources: list[SourceAttribution] = []
    timestamp: datetime


class ChatSession(BaseModel):
    id: str
    title: str
    messages: list[ChatMessage] = []
    created_at: datetime
    updated_at: datetime
