"""Public API for nexuspkm.models.

All model classes are re-exported here so that downstream code can
import directly from ``nexuspkm.models`` without knowing the submodule layout.
"""

from nexuspkm.models.chat import ChatMessage, ChatSession
from nexuspkm.models.document import (
    ChunkResult,
    Document,
    DocumentMetadata,
    EntityResult,
    ProcessingStatus,
    RelResult,
    RetrievalResult,
    ScoreFloat,
    SourceAttribution,
    SourceType,
)
from nexuspkm.models.entity import (
    EntitySummary,
    EntityType,
    ExtractedEntity,
    ExtractedRelationship,
    ExtractionResult,
)
from nexuspkm.models.relationship import RelationshipType
from nexuspkm.models.search import (
    DateBucket,
    EntityCount,
    SearchFacets,
    SearchFilters,
    SearchRequest,
    SearchResponse,
    SearchResult,
    TagCount,
)

__all__ = [
    # chat
    "ChatMessage",
    "ChatSession",
    # document
    "ChunkResult",
    "Document",
    "DocumentMetadata",
    "EntityResult",
    "ProcessingStatus",
    "RelResult",
    "RetrievalResult",
    "ScoreFloat",
    "SourceAttribution",
    "SourceType",
    # entity
    "EntitySummary",
    "EntityType",
    "ExtractedEntity",
    "ExtractedRelationship",
    "ExtractionResult",
    # relationship
    "RelationshipType",
    # search
    "DateBucket",
    "EntityCount",
    "SearchFacets",
    "SearchFilters",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "TagCount",
]
