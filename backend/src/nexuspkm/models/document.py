"""Core document and retrieval data models.

Defines the canonical Document schema shared across all layers:
connectors produce Document, the engine stores/retrieves it, and
retrieval returns ChunkResult/EntityResult/RelResult/RetrievalResult.

SourceAttribution lives here (rather than chat.py) because it is
used by both RetrievalResult and ChatMessage.

Spec: F-002 FR-1, FR-4, FR-5
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Self

from pydantic import AnyUrl, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from nexuspkm.models.entity import EntityType
from nexuspkm.models.relationship import RelationshipType

# Retrieval scores are in [0.0, 1.0]: combined_score is a weighted sum of
# vector(0.6) + graph(0.3) + recency(0.1); relevance_score is the same.
# ChunkResult.score (cosine similarity) is left unconstrained as it can
# exceed this range depending on the embedding model's normalisation.
ScoreFloat = Annotated[float, Field(ge=0.0, le=1.0)]


class SourceType(StrEnum):
    TEAMS_TRANSCRIPT = "teams_transcript"
    OBSIDIAN_NOTE = "obsidian_note"
    OUTLOOK_EMAIL = "outlook_email"
    OUTLOOK_CALENDAR = "outlook_calendar"
    JIRA_ISSUE = "jira_issue"
    APPLE_NOTE = "apple_note"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    ERROR = "error"


class DocumentMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_type: SourceType
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    author: str | None = None
    participants: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    url: AnyUrl | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    synced_at: AwareDatetime
    custom: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def updated_at_not_before_created_at(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be >= created_at")
        return self


class Document(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    # Connectors must supply at least a title or stub for empty-body sources
    # (e.g. calendar events with no body) before producing a Document.
    content: str = Field(min_length=1)
    metadata: DocumentMetadata
    chunks: list[str] = Field(default_factory=list)
    processing_status: ProcessingStatus = ProcessingStatus.PENDING


class SourceAttribution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_type: SourceType
    source_id: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)
    relevance_score: ScoreFloat
    created_at: AwareDatetime
    url: AnyUrl | None = None
    participants: list[str] = Field(default_factory=list)


class ChunkResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    # Cosine similarity; lower-bounded at -1.0 (unit-vector models) but can
    # exceed 1.0 for non-normalised embeddings, so not bounded above.
    score: float = Field(ge=-1.0)
    source_type: SourceType
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    created_at: AwareDatetime
    url: str | None = None


class EntityResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: str = Field(min_length=1)
    entity_type: EntityType
    name: str = Field(min_length=1)
    context: str = Field(min_length=1)


class RelResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_entity: str = Field(min_length=1)
    relationship_type: RelationshipType
    target_entity: str = Field(min_length=1)
    context: str = Field(min_length=1)


class RetrievalResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chunks: list[ChunkResult]
    entities: list[EntityResult]
    relationships: list[RelResult]
    combined_score: ScoreFloat
    sources: list[SourceAttribution]


class SyncState(BaseModel):
    """Connector sync checkpoint — persisted between sync runs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    last_synced_at: AwareDatetime | None = None
    cursor: str | None = None
    documents_synced: int = 0
    extra: dict[str, object] = Field(default_factory=dict)
