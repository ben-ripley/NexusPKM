"""Document ingestion pipeline.

Orchestrates: Document → chunks → embeddings → VectorStore + GraphStore.

Spec: F-002 FR-2, FR-3, FR-4
"""

from __future__ import annotations

import asyncio
import threading

import structlog

from nexuspkm.engine.chunking import DocumentChunker
from nexuspkm.engine.graph_store import DocumentNode, GraphStore
from nexuspkm.engine.vector_store import VectorChunk, VectorStore
from nexuspkm.models.document import Document, ProcessingStatus
from nexuspkm.providers.base import BaseEmbeddingProvider

logger = structlog.get_logger(__name__)


class IngestionPipeline:
    """Ingest documents into the dual-backend knowledge store.

    Kuzu (GraphStore) is a sync C++ extension. All graph operations are
    dispatched to a thread-pool executor under a threading.Lock to prevent
    concurrent access on the same connection.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        graph_store: GraphStore,
        embedding_provider: BaseEmbeddingProvider,
        chunker: DocumentChunker | None = None,
    ) -> None:
        self._vector_store = vector_store
        self._graph_store = graph_store
        self._embedding_provider = embedding_provider
        self._chunker = chunker if chunker is not None else DocumentChunker()
        self._graph_lock = threading.Lock()

    async def ingest(self, document: Document) -> Document:
        """Ingest a document into both stores.

        Steps:
        1. Chunk document.content into overlapping text segments.
        2. Embed all chunks in a single batch call (raises on failure; no partial writes).
        3. Store VectorChunks in LanceDB via merge_insert (idempotent).
        4. Upsert DocumentNode in Kuzu via MERGE (idempotent).
        5. Return updated Document with chunks populated and status=INDEXED.
        """
        log = logger.bind(document_id=document.id)
        log.info("ingestion.start")

        # 1. Chunk
        texts = self._chunker.chunk(document)

        # 2. Embed — single batch; if this raises, nothing has been written yet
        embed_response = await self._embedding_provider.embed(texts)
        vectors = embed_response.embeddings

        # 3. Build VectorChunks and store
        # chunk_id format: "{document_id}:{chunk_index}" (deterministic)
        chunks: list[VectorChunk] = [
            VectorChunk(
                chunk_id=f"{document.id}:{i}",
                document_id=document.id,
                text=text,
                vector=vector,
                source_type=document.metadata.source_type,
                source_id=document.metadata.source_id,
                title=document.metadata.title,
                created_at=document.metadata.created_at,
                updated_at=document.metadata.updated_at,
            )
            for i, (text, vector) in enumerate(zip(texts, vectors, strict=True))
        ]
        await self._vector_store.store(chunks)

        # 4. Upsert DocumentNode in Kuzu (sync → executor)
        doc_node = DocumentNode(
            id=document.id,
            title=document.metadata.title,
            source_type=document.metadata.source_type.value,
            source_id=document.metadata.source_id,
            created_at=document.metadata.created_at,
        )
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._graph_upsert, doc_node)

        # 5. Return updated Document
        updated = Document(
            id=document.id,
            content=document.content,
            metadata=document.metadata,
            chunks=texts,
            processing_status=ProcessingStatus.INDEXED,
        )
        log.info("ingestion.complete", chunk_count=len(texts))
        return updated

    async def delete(self, document_id: str) -> None:
        """Remove document from both stores."""
        log = logger.bind(document_id=document_id)
        log.info("ingestion.delete")
        await self._vector_store.delete(document_id)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._graph_delete, document_id)
        log.info("ingestion.deleted")

    # ------------------------------------------------------------------
    # Sync helpers (run inside executor under lock)
    # ------------------------------------------------------------------

    def _graph_upsert(self, node: DocumentNode) -> None:
        with self._graph_lock:
            self._graph_store.upsert_document(node)

    def _graph_delete(self, document_id: str) -> None:
        with self._graph_lock:
            self._graph_store.delete_node("Document", document_id)
