"""Search request and response models.

Defines the API contract for the search endpoint: filters, requests,
results, facets, and the full search response envelope.

Spec: F-007 FR-1
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import AnyUrl, AwareDatetime, BaseModel, Field, model_validator

from nexuspkm.models.document import ScoreFloat, SourceType
from nexuspkm.models.entity import EntitySummary, EntityType


class SearchFilters(BaseModel):
    source_types: list[SourceType] | None = None
    date_from: AwareDatetime | None = None
    date_to: AwareDatetime | None = None
    entities: list[str] | None = None
    tags: list[str] | None = None

    @model_validator(mode="after")
    def date_range_valid(self) -> Self:
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("date_from must be <= date_to")
        return self


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    filters: SearchFilters | None = None
    top_k: Annotated[int, Field(ge=1, le=200)] = 20
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
    source_types: dict[SourceType, int]
    date_histogram: list[DateBucket]
    top_entities: list[EntityCount]
    top_tags: list[TagCount]


class SearchResult(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    excerpt: str
    source_type: SourceType
    source_id: str = Field(min_length=1)
    relevance_score: ScoreFloat
    created_at: AwareDatetime
    url: AnyUrl | None = None
    matched_entities: list[EntitySummary] = Field(default_factory=list)
    related_documents: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total_count: int = Field(ge=0)
    facets: SearchFacets
    query_entities: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def total_count_at_least_results(self) -> Self:
        if self.total_count < len(self.results):
            raise ValueError(
                f"total_count ({self.total_count}) must be >= len(results) ({len(self.results)})"
            )
        return self
