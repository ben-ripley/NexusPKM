"""Entity and extraction data models.

Defines EntityType, EntitySummary (lightweight reference used in search results),
and the full extraction models produced by the entity intelligence layer.

Spec: F-006 FR-1, FR-2
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

from nexuspkm.models.relationship import RelationshipType

ConfidenceFloat = Annotated[float, Field(ge=0.0, le=1.0)]


class EntityType(StrEnum):
    PERSON = "person"
    PROJECT = "project"
    TOPIC = "topic"
    DECISION = "decision"
    ACTION_ITEM = "action_item"
    MEETING = "meeting"


class EntitySummary(BaseModel):
    name: str
    entity_type: EntityType


class ExtractedEntity(BaseModel):
    type: EntityType
    name: str
    properties: dict[str, object] = Field(default_factory=dict)
    confidence: ConfidenceFloat
    source_span: str


class ExtractedRelationship(BaseModel):
    source_entity: str
    relationship_type: RelationshipType
    target_entity: str
    confidence: ConfidenceFloat
    context: str


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity]
    relationships: list[ExtractedRelationship]
    confidence: ConfidenceFloat
