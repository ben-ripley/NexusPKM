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

from pydantic import AwareDatetime, BaseModel


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
    source_type: SourceType
    source_id: str
    title: str
    author: str | None = None
    participants: list[str] = []
    tags: list[str] = []
    url: str | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    synced_at: AwareDatetime
    custom: dict[str, object] = {}


class Document(BaseModel):
    id: str
    content: str
    metadata: DocumentMetadata
    chunks: list[str] = []
    processing_status: ProcessingStatus = ProcessingStatus.PENDING


class SourceAttribution(BaseModel):
    document_id: str
    title: str
    source_type: SourceType
    source_id: str
    excerpt: str
    relevance_score: float
    created_at: AwareDatetime
    url: str | None = None
    participants: list[str] = []


class ChunkResult(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float
    source_type: SourceType
    source_id: str
    title: str
    created_at: AwareDatetime


class EntityResult(BaseModel):
    entity_id: str
    entity_type: str
    name: str
    context: str


class RelResult(BaseModel):
    source_entity: str
    relationship_type: str
    target_entity: str
    context: str


class RetrievalResult(BaseModel):
    chunks: list[ChunkResult]
    entities: list[EntityResult]
    relationships: list[RelResult]
    combined_score: float
    sources: list[SourceAttribution]
