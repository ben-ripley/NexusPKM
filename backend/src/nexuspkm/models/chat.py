"""Chat session and message models.

Defines the data contracts for the chat interface: ChatMessage with
role-constrained Literal type, source attributions linking back to
documents, and ChatSession grouping messages into a conversation.

Spec: F-005 FR-3, FR-4
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from nexuspkm.models.document import SourceAttribution


class ChatMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)
    sources: list[SourceAttribution] = Field(default_factory=list)
    timestamp: AwareDatetime


class ChatSession(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def updated_at_not_before_created_at(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be >= created_at")
        return self
