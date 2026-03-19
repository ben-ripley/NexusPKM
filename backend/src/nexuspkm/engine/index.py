"""KnowledgeIndex — unified facade over ingestion and retrieval pipelines.

Named after LlamaIndex's PropertyGraphIndex; orchestrates both backends
(LanceDB vector store + Kuzu graph store) through a single interface.

Spec: F-002
"""

from __future__ import annotations

import asyncio
import re
import threading

import structlog

from nexuspkm.engine.chunking import DocumentChunker
from nexuspkm.engine.graph_store import GraphStore
from nexuspkm.engine.ingestion import IngestionPipeline
from nexuspkm.engine.retrieval import HybridRetriever
from nexuspkm.engine.vector_store import VectorStore
from nexuspkm.models.document import Document, RetrievalResult
from nexuspkm.models.search import SearchFilters
from nexuspkm.providers.base import BaseEmbeddingProvider

logger = structlog.get_logger(__name__)

# Validates that Cypher label/rel-type identifiers interpolated into queries
# contain only safe characters — mirrors the same guard in graph_store.py.
_SAFE_CYPHER_LABEL_RE: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Node tables that count as "entities" (excludes Document)
_ENTITY_TABLES = ("Person", "Project", "Topic", "Decision", "ActionItem", "Meeting")

# Mapping needed for relationship count queries
_REL_TABLE_ENDPOINTS: dict[str, tuple[str, str]] = {
    "ATTENDED": ("Person", "Meeting"),
    "MENTIONED_IN": ("Person", "Document"),
    "ASSIGNED_TO": ("ActionItem", "Person"),
    "RELATED_TO": ("Document", "Document"),
    "DECIDED_IN": ("Decision", "Meeting"),
    "WORKS_ON": ("Person", "Project"),
    "TAGGED_WITH": ("Document", "Topic"),
    "FOLLOWED_UP_BY": ("ActionItem", "ActionItem"),
    "OWNS": ("Person", "Project"),
    "BLOCKS": ("ActionItem", "ActionItem"),
}


class KnowledgeIndex:
    """Top-level facade: ingest and retrieve over the dual-backend knowledge store."""

    def __init__(
        self,
        vector_store: VectorStore,
        graph_store: GraphStore,
        embedding_provider: BaseEmbeddingProvider,
        chunker: DocumentChunker | None = None,
    ) -> None:
        self._vector_store = vector_store
        self._graph_store = graph_store
        # Single shared lock ensures mutual exclusion over the Kuzu connection
        # across concurrent ingest, retrieval, and stats operations.
        _graph_lock = threading.Lock()
        self._graph_lock = _graph_lock
        self._pipeline = IngestionPipeline(
            vector_store, graph_store, embedding_provider, chunker, graph_lock=_graph_lock
        )
        self._retriever = HybridRetriever(
            vector_store, graph_store, embedding_provider, graph_lock=_graph_lock
        )

    async def insert(self, document: Document) -> Document:
        """Ingest a document into both stores."""
        return await self._pipeline.ingest(document)

    async def delete(self, document_id: str) -> None:
        """Remove document from both stores."""
        await self._pipeline.delete(document_id)

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: SearchFilters | None = None,
    ) -> RetrievalResult:
        """Hybrid retrieval: vector similarity + graph context."""
        return await self._retriever.retrieve(query, top_k=top_k, filters=filters)

    async def stats(self) -> dict[str, int]:
        """Return store statistics: documents, chunks, entities, relationships."""
        chunks = await self._vector_store.count()
        loop = asyncio.get_running_loop()
        graph_stats: dict[str, int] = await loop.run_in_executor(None, self._count_graph_stats)
        return {
            "chunks": chunks,
            **graph_stats,
        }

    # ------------------------------------------------------------------
    # Sync helper (run inside executor under lock)
    # ------------------------------------------------------------------

    def _count_graph_stats(self) -> dict[str, int]:
        with self._graph_lock:
            doc_rows = self._graph_store.execute("MATCH (n:Document) RETURN count(n) AS cnt")
            documents = int(doc_rows[0]["cnt"]) if doc_rows else 0

            entities = 0
            for table in _ENTITY_TABLES:
                # Validate before interpolation — defence-in-depth against accidental
                # extension of _ENTITY_TABLES with unsafe values.
                if not _SAFE_CYPHER_LABEL_RE.match(table):
                    raise ValueError(f"Unsafe entity table name: {table!r}")
                rows = self._graph_store.execute(f"MATCH (n:{table}) RETURN count(n) AS cnt")
                entities += int(rows[0]["cnt"]) if rows else 0

            relationships = 0
            for rel, (from_t, to_t) in _REL_TABLE_ENDPOINTS.items():
                for label in (rel, from_t, to_t):
                    if not _SAFE_CYPHER_LABEL_RE.match(label):
                        raise ValueError(f"Unsafe Cypher label: {label!r}")
                rows = self._graph_store.execute(
                    f"MATCH (a:{from_t})-[r:{rel}]->(b:{to_t}) RETURN count(r) AS cnt"
                )
                relationships += int(rows[0]["cnt"]) if rows else 0

        return {
            "documents": documents,
            "entities": entities,
            "relationships": relationships,
        }
