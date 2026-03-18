"""Search request and response models.

Defines the API contract for the search endpoint: filters, requests,
results, facets, and the full search response envelope.

Spec: F-007 FR-1
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, Field

from nexuspkm.models.document import SourceType
from nexuspkm.models.entity import EntitySummary, EntityType


class SearchFilters(BaseModel):
    source_types: list[SourceType] | None = None
    date_from: AwareDatetime | None = None
    date_to: AwareDatetime | None = None
    entities: list[str] | None = None
    tags: list[str] | None = None


class SearchRequest(BaseModel):
    query: str
    filters: SearchFilters | None = None
    top_k: int = Field(default=20, ge=1)
    include_graph_expansion: bool = True


class DateBucket(BaseModel):
    date: AwareDatetime
    count: int


class EntityCount(BaseModel):
    name: str
    entity_type: EntityType
    count: int


class TagCount(BaseModel):
    tag: str
    count: int


class SearchFacets(BaseModel):
    source_types: dict[str, int]
    date_histogram: list[DateBucket]
    top_entities: list[EntityCount]
    top_tags: list[TagCount]


class SearchResult(BaseModel):
    id: str
    title: str
    excerpt: str
    source_type: SourceType
    source_id: str
    relevance_score: float
    created_at: AwareDatetime
    url: str | None = None
    matched_entities: list[EntitySummary] = []
    related_documents: list[str] = []


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total_count: int
    facets: SearchFacets
    query_entities: list[str] = []
