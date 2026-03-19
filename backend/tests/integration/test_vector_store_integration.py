"""Integration tests for VectorStore using real LanceDB on tmp_path.

All tests use real file I/O — no mocks.
Spec: F-002 FR-3
"""

from __future__ import annotations

import datetime
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from nexuspkm.engine.vector_store import SearchFilters, VectorChunk, VectorStore
from nexuspkm.models.document import SourceType

NOW = datetime.datetime(2026, 3, 18, 12, 0, 0, tzinfo=datetime.UTC)


def _make_chunk(chunk_id: str = "c1", document_id: str = "d1", **kwargs: object) -> VectorChunk:
    defaults: dict[str, object] = {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "text": "Sample text",
        "vector": [0.1, 0.2, 0.3, 0.4],
        "source_type": SourceType.JIRA_ISSUE,
        "source_id": "NXP-1",
        "title": "Test Doc",
        "created_at": NOW,
        "updated_at": NOW,
    }
    defaults.update(kwargs)
    return VectorChunk(**defaults)


@pytest.fixture
async def vs(tmp_path: Path) -> AsyncGenerator[VectorStore, None]:
    store = VectorStore(db_path=str(tmp_path / "lancedb"), dimensions=4)
    await store._open()
    yield store
    await store.close()


class TestIntegrationStoreAndSearch:
    async def test_store_then_search_returns_top_result(self, vs: VectorStore) -> None:
        chunk = _make_chunk()
        await vs.store([chunk])
        results = await vs.search([0.1, 0.2, 0.3, 0.4], top_k=5)
        assert len(results) == 1
        assert results[0].chunk_id == "c1"
        assert results[0].document_id == "d1"

    async def test_store_then_delete_then_search_returns_empty(self, vs: VectorStore) -> None:
        chunk = _make_chunk()
        await vs.store([chunk])
        await vs.delete("d1")
        results = await vs.search([0.1, 0.2, 0.3, 0.4], top_k=5)
        assert results == []

    async def test_search_with_source_type_filter(self, vs: VectorStore) -> None:
        chunk_jira = _make_chunk("c1", "d1", source_type=SourceType.JIRA_ISSUE)
        chunk_obs = _make_chunk(
            "c2", "d2", source_type=SourceType.OBSIDIAN_NOTE, vector=[0.5, 0.6, 0.7, 0.8]
        )
        await vs.store([chunk_jira, chunk_obs])

        filters = SearchFilters(source_type=SourceType.JIRA_ISSUE)
        results = await vs.search([0.1, 0.2, 0.3, 0.4], top_k=5, filters=filters)
        assert all(r.source_type == SourceType.JIRA_ISSUE for r in results)
        assert len(results) == 1

    async def test_count_after_store_and_delete(self, vs: VectorStore) -> None:
        c1 = _make_chunk("c1", "d1")
        c2 = _make_chunk("c2", "d2", vector=[0.5, 0.6, 0.7, 0.8])
        await vs.store([c1, c2])
        assert await vs.count() == 2
        await vs.delete("d1")
        assert await vs.count() == 1

    async def test_store_is_idempotent_same_chunk_id_overwrites(self, vs: VectorStore) -> None:
        c1 = _make_chunk("c1", "d1", text="original")
        await vs.store([c1])
        assert await vs.count() == 1

        c1_updated = _make_chunk("c1", "d1", text="updated")
        await vs.store([c1_updated])
        assert await vs.count() == 1

        results = await vs.search([0.1, 0.2, 0.3, 0.4], top_k=1)
        assert results[0].text == "updated"

    async def test_search_score_is_in_valid_range(self, vs: VectorStore) -> None:
        chunk = _make_chunk()
        await vs.store([chunk])
        results = await vs.search([0.1, 0.2, 0.3, 0.4], top_k=5)
        assert len(results) == 1
        assert -1.0 <= results[0].score <= 1.0
