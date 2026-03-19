"""Integration tests for KnowledgeIndex using real LanceDB + Kuzu on tmp_path.

Spec: F-002
"""

from __future__ import annotations

import datetime
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nexuspkm.engine.graph_store import GraphStore
from nexuspkm.engine.index import KnowledgeIndex
from nexuspkm.engine.vector_store import VectorStore
from nexuspkm.models.document import Document, DocumentMetadata, ProcessingStatus, SourceType
from nexuspkm.providers.base import EmbeddingResponse

NOW = datetime.datetime(2026, 3, 18, 12, 0, 0, tzinfo=datetime.UTC)
DIM = 4


def _fake_embed(texts: list[str]) -> EmbeddingResponse:
    vectors = [[float(i % 10) / 10, 0.2, 0.3, 0.4] for i in range(len(texts))]
    return EmbeddingResponse(embeddings=vectors, provider="fake", model="fake", dimensions=DIM)


def _make_doc(doc_id: str = "d1", title: str = "Test Note") -> Document:
    return Document(
        id=doc_id,
        content="This is a test document with some content for indexing.",
        metadata=DocumentMetadata(
            source_type=SourceType.OBSIDIAN_NOTE,
            source_id=f"note-{doc_id}",
            title=title,
            created_at=NOW,
            updated_at=NOW,
            synced_at=NOW,
        ),
    )


@pytest.fixture
async def index(tmp_path: Path) -> AsyncGenerator[KnowledgeIndex, None]:
    vs = VectorStore(db_path=str(tmp_path / "lancedb"), dimensions=DIM)
    await vs._open()
    gs = GraphStore(db_path=tmp_path / "kuzu")

    embedding_provider = MagicMock()
    embedding_provider.embed = AsyncMock(side_effect=lambda texts: _fake_embed(texts))
    embedding_provider.embed_single = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])
    embedding_provider.dimension = DIM

    ki = KnowledgeIndex(vs, gs, embedding_provider)
    yield ki
    await vs.close()
    gs.close()


class TestKnowledgeIndexInsert:
    async def test_insert_returns_indexed_document(self, index: KnowledgeIndex) -> None:
        doc = _make_doc()
        result = await index.insert(doc)
        assert result.processing_status == ProcessingStatus.INDEXED

    async def test_insert_populates_both_stores(self, index: KnowledgeIndex) -> None:
        doc = _make_doc()
        await index.insert(doc)
        stats = await index.stats()
        assert stats["chunks"] > 0
        assert stats["documents"] == 1

    async def test_insert_multiple_documents(self, index: KnowledgeIndex) -> None:
        await index.insert(_make_doc("d1", "Doc One"))
        await index.insert(_make_doc("d2", "Doc Two"))
        stats = await index.stats()
        assert stats["documents"] == 2


class TestKnowledgeIndexDelete:
    async def test_delete_removes_from_both_stores(self, index: KnowledgeIndex) -> None:
        doc = _make_doc()
        await index.insert(doc)
        await index.delete(doc.id)
        stats = await index.stats()
        assert stats["chunks"] == 0
        assert stats["documents"] == 0

    async def test_delete_non_existent_document_does_not_raise(self, index: KnowledgeIndex) -> None:
        await index.delete("nonexistent-id")


class TestKnowledgeIndexStats:
    async def test_stats_returns_required_keys(self, index: KnowledgeIndex) -> None:
        stats = await index.stats()
        assert set(stats.keys()) == {"chunks", "documents", "entities", "relationships"}

    async def test_stats_empty_index(self, index: KnowledgeIndex) -> None:
        stats = await index.stats()
        assert stats["chunks"] == 0
        assert stats["documents"] == 0
        assert stats["entities"] == 0
        assert stats["relationships"] == 0

    async def test_stats_after_insert(self, index: KnowledgeIndex) -> None:
        await index.insert(_make_doc())
        stats = await index.stats()
        assert stats["chunks"] > 0
        assert stats["documents"] == 1
        assert stats["entities"] == 0  # entity extraction is NXP-60
        assert stats["relationships"] == 0
