"""Hybrid retrieval combining vector similarity and graph context.

Implements F-002 FR-5 scoring:
    combined_score = vector(0.6) + graph(0.3) + recency(0.1)

Spec: F-002 FR-5
"""

from __future__ import annotations

import asyncio
import threading
from typing import NamedTuple

import structlog

from nexuspkm.engine.graph_store import GraphStore
from nexuspkm.engine.vector_store import SearchFilters as VectorSearchFilters
from nexuspkm.engine.vector_store import VectorStore
from nexuspkm.models.document import (
    ChunkResult,
    EntityResult,
    RelResult,
    RetrievalResult,
    SourceAttribution,
)
from nexuspkm.models.entity import EntityType
from nexuspkm.models.relationship import RelationshipType
from nexuspkm.models.search import SearchFilters
from nexuspkm.providers.base import BaseEmbeddingProvider

logger = structlog.get_logger(__name__)

# Scoring weights (must sum to 1.0)
_VECTOR_WEIGHT = 0.6
_GRAPH_WEIGHT = 0.3
_RECENCY_WEIGHT = 0.1

# Maximum characters included in a SourceAttribution excerpt (spec: F-002 FR-5)
_EXCERPT_MAX_CHARS: int = 200

# Maximum query characters written to structured logs (avoids PII / log bloat)
_LOG_QUERY_MAX_LEN: int = 80


class _GraphData(NamedTuple):
    boost: dict[str, float]
    entities: list[EntityResult]
    relationships: list[RelResult]


class HybridRetriever:
    """Retrieve from vector + graph stores and merge with weighted scoring."""

    def __init__(
        self,
        vector_store: VectorStore,
        graph_store: GraphStore,
        embedding_provider: BaseEmbeddingProvider,
        *,
        graph_boost_max_connections: int = 5,
        graph_lock: threading.Lock | None = None,
    ) -> None:
        self._vector_store = vector_store
        self._graph_store = graph_store
        self._embedding_provider = embedding_provider
        # Number of graph connections (RELATED_TO + TAGGED_WITH) that yields
        # a full boost of 1.0; tunable per deployment.
        self._graph_boost_max = graph_boost_max_connections
        # Accept a shared lock so KnowledgeIndex can serialise all Kuzu access
        # through one lock when pipeline, retriever, and stats run concurrently.
        self._graph_lock = graph_lock if graph_lock is not None else threading.Lock()

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: SearchFilters | None = None,
    ) -> RetrievalResult:
        """Hybrid retrieval: embed query → vector search → graph expansion → merge."""
        log = logger.bind(query=query[:_LOG_QUERY_MAX_LEN], top_k=top_k)
        log.info("retrieval.start")

        # 1. Embed query
        query_vector = await self._embedding_provider.embed_single(query)

        # 2. Vector search (fetch top_k * 2 candidates before re-ranking)
        vector_filters = _to_vector_filters(filters)
        raw_chunks = await self._vector_store.search(
            query_vector, top_k=top_k * 2, filters=vector_filters
        )

        # Apply multi-source-type post-filter if needed
        if filters is not None and filters.source_types and len(filters.source_types) > 1:
            allowed = set(filters.source_types)
            raw_chunks = [c for c in raw_chunks if c.source_type in allowed]

        if not raw_chunks:
            log.info("retrieval.empty")
            return RetrievalResult(
                chunks=[],
                entities=[],
                relationships=[],
                combined_score=0.0,
                sources=[],
            )

        # 3. Graph context (sync Kuzu → executor)
        doc_ids = list({c.document_id for c in raw_chunks})
        loop = asyncio.get_running_loop()
        graph_data: _GraphData = await loop.run_in_executor(None, self._fetch_graph_data, doc_ids)

        # 4. Recency scores: normalize created_at within result window
        recency = _compute_recency(raw_chunks)

        # 5. Score each chunk
        scored: list[tuple[float, ChunkResult]] = []
        for chunk in raw_chunks:
            graph_boost = graph_data.boost.get(chunk.document_id, 0.0)
            combined = (
                _VECTOR_WEIGHT * chunk.score
                + _GRAPH_WEIGHT * graph_boost
                + _RECENCY_WEIGHT * recency.get(chunk.chunk_id, 0.0)
            )
            combined = max(0.0, min(1.0, combined))
            scored.append((combined, chunk))

        # 6. Sort descending, deduplicate by chunk_id, take top_k
        scored.sort(key=lambda t: t[0], reverse=True)
        seen: set[str] = set()
        top_chunks: list[ChunkResult] = []
        top_scores: list[float] = []
        for score, chunk in scored:
            if chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)
            top_chunks.append(chunk)
            top_scores.append(score)
            if len(top_chunks) >= top_k:
                break

        # 7. Build SourceAttribution list
        sources: list[SourceAttribution] = [
            SourceAttribution(
                document_id=chunk.document_id,
                title=chunk.title,
                source_type=chunk.source_type,
                source_id=chunk.source_id,
                excerpt=chunk.text[:_EXCERPT_MAX_CHARS],
                relevance_score=score,
                created_at=chunk.created_at,
            )
            for chunk, score in zip(top_chunks, top_scores, strict=True)
        ]

        overall_score = top_scores[0] if top_scores else 0.0

        log.info("retrieval.complete", result_count=len(top_chunks))
        return RetrievalResult(
            chunks=top_chunks,
            entities=graph_data.entities,
            relationships=graph_data.relationships,
            combined_score=overall_score,
            sources=sources,
        )

    # ------------------------------------------------------------------
    # Sync helpers (run inside executor under lock)
    # ------------------------------------------------------------------

    def _fetch_graph_data(self, doc_ids: list[str]) -> _GraphData:
        """Query graph store for boost data and entity/relationship context.

        The lock is held for the full loop over doc_ids. For a local single-user
        deployment the default result set (top_k * 2 = 20 docs, each requiring
        two lightweight Kuzu lookups) holds the lock for ~2 ms in practice.
        For multi-user deployments consider batching these into a single Cypher
        query to reduce lock hold time.
        """
        with self._graph_lock:
            boost: dict[str, float] = {}
            entities: list[EntityResult] = []
            relationships: list[RelResult] = []

            for doc_id in doc_ids:
                related = self._graph_store.get_relationships("RELATED_TO", from_id=doc_id)
                tagged = self._graph_store.get_relationships("TAGGED_WITH", from_id=doc_id)
                count = len(related) + len(tagged)
                boost[doc_id] = min(1.0, float(count) / self._graph_boost_max)

                for rel in tagged:
                    topic = self._graph_store.get_topic(rel["to_id"])
                    if topic:
                        entities.append(
                            EntityResult(
                                entity_id=topic.id,
                                entity_type=EntityType.TOPIC,
                                name=topic.name,
                                context=f"tagged in document {doc_id}",
                            )
                        )

                for rel in related:
                    relationships.append(
                        RelResult(
                            source_entity=doc_id,
                            relationship_type=RelationshipType.RELATED_TO,
                            target_entity=rel["to_id"],
                            context="document relationship",
                        )
                    )

        return _GraphData(boost=boost, entities=entities, relationships=relationships)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _to_vector_filters(filters: SearchFilters | None) -> VectorSearchFilters | None:
    """Convert search model filters to the vector store's filter schema."""
    if filters is None:
        return None
    # VectorSearchFilters only supports a single source_type; pass it only
    # when the caller specifies exactly one type (multi-type handled post-search).
    source_type = None
    if filters.source_types and len(filters.source_types) == 1:
        source_type = filters.source_types[0]
    if source_type is None and filters.date_from is None and filters.date_to is None:
        return None
    return VectorSearchFilters(
        source_type=source_type,
        date_from=filters.date_from,
        date_to=filters.date_to,
    )


def _compute_recency(chunks: list[ChunkResult]) -> dict[str, float]:
    """Normalise created_at timestamps to [0.0, 1.0]; newest = 1.0."""
    if not chunks:
        return {}
    timestamps = [c.created_at.timestamp() for c in chunks]
    min_ts = min(timestamps)
    max_ts = max(timestamps)
    if max_ts == min_ts:
        return {c.chunk_id: 1.0 for c in chunks}
    span = max_ts - min_ts
    return {c.chunk_id: (c.created_at.timestamp() - min_ts) / span for c in chunks}
