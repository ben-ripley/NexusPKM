"""Integration tests for HybridRetriever using real LanceDB + Kuzu on tmp_path.

Spec: F-002 FR-5
"""

from __future__ import annotations

import datetime
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nexuspkm.engine.graph_store import GraphStore
from nexuspkm.engine.ingestion import IngestionPipeline
from nexuspkm.engine.retrieval import HybridRetriever
from nexuspkm.engine.vector_store import VectorStore
from nexuspkm.models.document import Document, DocumentMetadata, SourceType
from nexuspkm.providers.base import EmbeddingResponse

NOW = datetime.datetime(2026, 3, 18, 12, 0, 0, tzinfo=datetime.UTC)
DIM = 4

# Fixed query vector for deterministic search results
QUERY_VECTOR = [0.1, 0.2, 0.3, 0.4]


def _fake_embed(texts: list[str]) -> EmbeddingResponse:
    # All chunks get the same vector for predictable nearest-neighbour results
    vectors = [QUERY_VECTOR[:] for _ in texts]
    return EmbeddingResponse(embeddings=vectors, provider="fake", model="fake", dimensions=DIM)


def _make_doc(doc_id: str = "d1", title: str = "Test Document") -> Document:
    return Document(
        id=doc_id,
        content="This document discusses project planning and implementation details.",
        metadata=DocumentMetadata(
            source_type=SourceType.OBSIDIAN_NOTE,
            source_id=f"src-{doc_id}",
            title=title,
            created_at=NOW,
            updated_at=NOW,
            synced_at=NOW,
        ),
    )


@pytest.fixture
async def stores(
    tmp_path: Path,
) -> AsyncGenerator[tuple[VectorStore, GraphStore], None]:
    vs = VectorStore(db_path=str(tmp_path / "lancedb"), dimensions=DIM)
    gs = GraphStore(db_path=tmp_path / "kuzu")
    try:
        yield vs, gs
    finally:
        await vs.close()
        gs.close()


@pytest.fixture
def embedding_provider() -> MagicMock:
    provider = MagicMock()
    provider.embed = AsyncMock(side_effect=lambda texts: _fake_embed(texts))
    provider.embed_single = AsyncMock(return_value=QUERY_VECTOR)
    provider.dimension = DIM
    return provider


class TestRetrievalIntegration:
    async def test_retrieve_returns_ingested_document(
        self,
        stores: tuple[VectorStore, GraphStore],
        embedding_provider: MagicMock,
    ) -> None:
        vs, gs = stores
        pipeline = IngestionPipeline(vs, gs, embedding_provider)
        retriever = HybridRetriever(vs, gs, embedding_provider)

        doc = _make_doc("d1", "Project Plan")
        await pipeline.ingest(doc)

        result = await retriever.retrieve("project planning", top_k=5)

        assert len(result.chunks) > 0
        doc_ids = {c.document_id for c in result.chunks}
        assert "d1" in doc_ids

    async def test_retrieve_top_k_limits_results(
        self,
        stores: tuple[VectorStore, GraphStore],
        embedding_provider: MagicMock,
    ) -> None:
        vs, gs = stores
        pipeline = IngestionPipeline(vs, gs, embedding_provider)
        retriever = HybridRetriever(vs, gs, embedding_provider)

        for i in range(5):
            await pipeline.ingest(_make_doc(f"d{i}", f"Document {i}"))

        result = await retriever.retrieve("project", top_k=2)

        assert len(result.chunks) <= 2

    async def test_retrieve_returns_sources_matching_chunks(
        self,
        stores: tuple[VectorStore, GraphStore],
        embedding_provider: MagicMock,
    ) -> None:
        vs, gs = stores
        pipeline = IngestionPipeline(vs, gs, embedding_provider)
        retriever = HybridRetriever(vs, gs, embedding_provider)

        await pipeline.ingest(_make_doc())

        result = await retriever.retrieve("project", top_k=5)

        assert len(result.sources) == len(result.chunks)
        chunk_doc_ids = {c.document_id for c in result.chunks}
        source_doc_ids = {s.document_id for s in result.sources}
        assert chunk_doc_ids == source_doc_ids

    async def test_retrieve_after_delete_returns_no_results(
        self,
        stores: tuple[VectorStore, GraphStore],
        embedding_provider: MagicMock,
    ) -> None:
        vs, gs = stores
        pipeline = IngestionPipeline(vs, gs, embedding_provider)
        retriever = HybridRetriever(vs, gs, embedding_provider)

        doc = _make_doc()
        await pipeline.ingest(doc)
        await pipeline.delete(doc.id)

        result = await retriever.retrieve("project planning", top_k=5)
        assert result.chunks == []

    async def test_retrieve_combined_score_in_valid_range(
        self,
        stores: tuple[VectorStore, GraphStore],
        embedding_provider: MagicMock,
    ) -> None:
        vs, gs = stores
        pipeline = IngestionPipeline(vs, gs, embedding_provider)
        retriever = HybridRetriever(vs, gs, embedding_provider)

        await pipeline.ingest(_make_doc())

        result = await retriever.retrieve("test query", top_k=5)

        assert 0.0 <= result.combined_score <= 1.0
        for source in result.sources:
            assert 0.0 <= source.relevance_score <= 1.0

    async def test_retrieve_empty_store_returns_empty_result(
        self,
        stores: tuple[VectorStore, GraphStore],
        embedding_provider: MagicMock,
    ) -> None:
        vs, gs = stores
        retriever = HybridRetriever(vs, gs, embedding_provider)

        result = await retriever.retrieve("anything", top_k=5)

        assert result.chunks == []
        assert result.combined_score == 0.0
