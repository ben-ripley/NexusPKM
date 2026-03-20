"""Search API endpoints.

Exposes:
  POST /api/search          semantic search over the knowledge index
  GET  /api/search/suggest  autocomplete suggestions from entity names
  GET  /api/search/facets   available facet values for the filter UI

Spec: F-007
"""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from nexuspkm.api.engine import get_knowledge_index
from nexuspkm.engine.graph_store import GraphStore
from nexuspkm.engine.index import KnowledgeIndex
from nexuspkm.models.document import (
    RetrievalResult,
    SourceAttribution,
    SourceType,
)
from nexuspkm.models.entity import EntityType
from nexuspkm.models.search import (
    DateBucket,
    EntityCount,
    SearchFacets,
    SearchRequest,
    SearchResponse,
    SearchResult,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])

# Hardcoded Cypher queries for autocomplete — one per node table.
# Using explicit literals avoids any f-string interpolation into Cypher.
# Only the $prefix value is user-supplied and is passed as a parameter.
_SUGGEST_QUERIES: Final[list[str]] = [
    "MATCH (n:Person) WHERE toLower(n.name) STARTS WITH toLower($prefix)"
    " RETURN n.name AS name LIMIT 10",
    "MATCH (n:Project) WHERE toLower(n.name) STARTS WITH toLower($prefix)"
    " RETURN n.name AS name LIMIT 10",
    "MATCH (n:Topic) WHERE toLower(n.name) STARTS WITH toLower($prefix)"
    " RETURN n.name AS name LIMIT 10",
]

_ALL_SOURCE_TYPES: Final[list[str]] = [st.value for st in SourceType]


# ---------------------------------------------------------------------------
# Dependency providers (overridden in main.py lifespan)
# ---------------------------------------------------------------------------


def get_graph_store() -> GraphStore:
    """Dependency: returns the active GraphStore."""
    raise HTTPException(  # pragma: no cover
        status_code=503, detail="Graph store not initialised"
    )


# ---------------------------------------------------------------------------
# POST /api/search
# ---------------------------------------------------------------------------


@router.post("", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    index: Annotated[KnowledgeIndex, Depends(get_knowledge_index)],
) -> SearchResponse:
    """Semantic search over the knowledge index."""
    result: RetrievalResult = await index.retrieve(
        request.query, top_k=request.top_k, filters=request.filters
    )

    results = [_source_to_result(s) for s in result.sources]
    facets = _build_facets(result)

    return SearchResponse(
        results=results,
        total_count=len(results),
        facets=facets,
        query_entities=[],
    )


def _source_to_result(source: SourceAttribution) -> SearchResult:
    return SearchResult(
        id=source.document_id,
        title=source.title,
        excerpt=source.excerpt,
        source_type=source.source_type,
        source_id=source.source_id,
        relevance_score=source.relevance_score,
        created_at=source.created_at,
        url=source.url,
        matched_entities=[],
        related_documents=[],
    )


def _build_facets(result: RetrievalResult) -> SearchFacets:
    # Single pass over chunks to compute source type counts and date histogram.
    # ChunkResult.created_at is a required AwareDatetime field and is never None.
    source_type_counts: Counter[SourceType] = Counter()
    month_counts: Counter[str] = Counter()
    month_datetimes: dict[str, DateBucket] = {}

    for chunk in result.chunks:
        source_type_counts[chunk.source_type] += 1
        dt = chunk.created_at
        month_key = f"{dt.year}-{dt.month:02d}"
        month_counts[month_key] += 1
        if month_key not in month_datetimes:
            first_of_month = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            month_datetimes[month_key] = DateBucket(date=first_of_month, count=0)

    date_histogram = [
        DateBucket(date=month_datetimes[k].date, count=month_counts[k])
        for k in sorted(month_counts.keys())
    ]

    # top_entities: aggregate entity counts from retrieval result
    entity_tracker: dict[str, tuple[EntityType, int]] = {}
    for e in result.entities:
        if e.name in entity_tracker:
            prev_type, prev_count = entity_tracker[e.name]
            entity_tracker[e.name] = (prev_type, prev_count + 1)
        else:
            entity_tracker[e.name] = (e.entity_type, 1)

    top_entities = sorted(
        [
            EntityCount(name=name, entity_type=etype, count=count)
            for name, (etype, count) in entity_tracker.items()
        ],
        key=lambda x: x.count,
        reverse=True,
    )[:10]

    return SearchFacets(
        source_types=dict(source_type_counts),
        date_histogram=date_histogram,
        top_entities=top_entities,
        top_tags=[],
    )


# ---------------------------------------------------------------------------
# GET /api/search/suggest
# ---------------------------------------------------------------------------


@router.get("/suggest", response_model=list[str])
async def suggest(
    q: Annotated[str, Query(min_length=1, max_length=100)],
    graph_store: Annotated[GraphStore, Depends(get_graph_store)],
) -> list[str]:
    """Return entity name suggestions matching the given prefix."""
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _suggest_sync, graph_store, q)
    except Exception:
        log.warning("search.suggest_failed", prefix=q, exc_info=True)
        return []


def _suggest_sync(graph_store: GraphStore, prefix: str) -> list[str]:
    names: set[str] = set()
    for query in _SUGGEST_QUERIES:
        try:
            rows = graph_store.execute(query, {"prefix": prefix})
            for row in rows:
                val = row.get("name")
                if val:
                    names.add(str(val))
        except Exception as exc:  # noqa: BLE001
            log.debug("search.suggest_query_failed", prefix=prefix, error=str(exc))
    return sorted(names)[:10]


# ---------------------------------------------------------------------------
# GET /api/search/facets
# ---------------------------------------------------------------------------


@router.get("/facets", response_model=dict[str, list[str]])
async def facets() -> dict[str, list[str]]:
    """Return available facet values for the filter sidebar.

    Static endpoint — does not query the database. Allows the filter UI
    to render before any search has been run.
    """
    return {"source_types": _ALL_SOURCE_TYPES}
