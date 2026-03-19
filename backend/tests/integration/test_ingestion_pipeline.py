"""Integration tests for IngestionPipeline using real LanceDB + Kuzu on tmp_path.

Spec: F-002 FR-2, FR-3, FR-4
"""

from __future__ import annotations

import datetime
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nexuspkm.engine.graph_store import GraphStore
from nexuspkm.engine.ingestion import IngestionPipeline
from nexuspkm.engine.vector_store import VectorStore
from nexuspkm.models.document import Document, DocumentMetadata, ProcessingStatus, SourceType
from nexuspkm.providers.base import EmbeddingResponse

NOW = datetime.datetime(2026, 3, 18, 12, 0, 0, tzinfo=datetime.UTC)
DIM = 4


def _fake_embed(texts: list[str]) -> EmbeddingResponse:
    vectors = [[float(i % 10) / 10, 0.2, 0.3, 0.4] for i in range(len(texts))]
    return EmbeddingResponse(embeddings=vectors, provider="fake", model="fake", dimensions=DIM)


def _make_doc(
    doc_id: str = "d1", content: str = "Hello world. This is a test document."
) -> Document:
    return Document(
        id=doc_id,
        content=content,
        metadata=DocumentMetadata(
            source_type=SourceType.OBSIDIAN_NOTE,
            source_id="note-1",
            title="Test Note",
            created_at=NOW,
            updated_at=NOW,
            synced_at=NOW,
        ),
    )


@pytest.fixture
async def pipeline(tmp_path: Path) -> AsyncGenerator[IngestionPipeline, None]:
    vs = VectorStore(db_path=str(tmp_path / "lancedb"), dimensions=DIM)
    gs = GraphStore(db_path=tmp_path / "kuzu")

    embedding_provider = MagicMock()
    embedding_provider.embed = AsyncMock(side_effect=lambda texts: _fake_embed(texts))

    pipe = IngestionPipeline(vs, gs, embedding_provider)
    try:
        yield pipe
    finally:
        await vs.close()
        gs.close()


class TestIngestionPipeline:
    async def test_ingest_returns_indexed_document(self, pipeline: IngestionPipeline) -> None:
        doc = _make_doc()
        result = await pipeline.ingest(doc)
        assert result.processing_status == ProcessingStatus.INDEXED
        assert result.id == doc.id

    async def test_ingest_populates_chunks(self, pipeline: IngestionPipeline) -> None:
        doc = _make_doc()
        result = await pipeline.ingest(doc)
        assert len(result.chunks) > 0

    async def test_ingest_stores_chunks_in_vector_store(self, pipeline: IngestionPipeline) -> None:
        doc = _make_doc()
        result = await pipeline.ingest(doc)
        count = await pipeline._vector_store.count()
        assert count == len(result.chunks)

    async def test_ingest_upserts_document_in_graph_store(
        self, pipeline: IngestionPipeline
    ) -> None:
        doc = _make_doc()
        await pipeline.ingest(doc)
        node = pipeline._graph_store.get_document(doc.id)
        assert node is not None
        assert node.id == doc.id
        assert node.title == doc.metadata.title

    async def test_ingest_is_idempotent(self, pipeline: IngestionPipeline) -> None:
        doc = _make_doc()
        await pipeline.ingest(doc)
        await pipeline.ingest(doc)
        # Same chunk_ids → merge_insert overwrites, not doubles
        result = await pipeline.ingest(doc)
        final_count = await pipeline._vector_store.count()
        assert final_count == len(result.chunks)

    async def test_delete_removes_from_both_stores(self, pipeline: IngestionPipeline) -> None:
        doc = _make_doc()
        await pipeline.ingest(doc)
        await pipeline.delete(doc.id)

        count = await pipeline._vector_store.count()
        assert count == 0

        node = pipeline._graph_store.get_document(doc.id)
        assert node is None

    async def test_ingest_embedding_failure_leaves_no_partial_writes(
        self, pipeline: IngestionPipeline
    ) -> None:
        pipeline._embedding_provider.embed = AsyncMock(side_effect=RuntimeError("embed failed"))
        doc = _make_doc()
        with pytest.raises(RuntimeError, match="embed failed"):
            await pipeline.ingest(doc)

        # Nothing should be written
        count = await pipeline._vector_store.count()
        assert count == 0

    async def test_chunk_ids_are_deterministic(self, pipeline: IngestionPipeline) -> None:
        doc = _make_doc()
        result = await pipeline.ingest(doc)
        expected_ids = [f"{doc.id}:{i}" for i in range(len(result.chunks))]
        # Re-fetch from vector store by searching
        query_vector = [0.0, 0.2, 0.3, 0.4]
        results = await pipeline._vector_store.search(query_vector, top_k=100)
        stored_ids = sorted(r.chunk_id for r in results)
        assert sorted(expected_ids) == stored_ids
