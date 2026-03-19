"""Integration tests for VectorStore using real LanceDB on tmp_path.

All tests use real file I/O — no mocks.
Spec: F-002 FR-3
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

NOW = datetime.datetime(2026, 3, 18, 12, 0, 0, tzinfo=datetime.UTC)
LATER = datetime.datetime(2026, 3, 19, 12, 0, 0, tzinfo=datetime.UTC)


def _make_chunk(chunk_id: str = "c1", document_id: str = "d1", **kwargs: object) -> object:
    from nexuspkm.engine.vector_store import VectorChunk

    defaults: dict[str, object] = {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "text": "Sample text",
        "vector": [0.1, 0.2, 0.3, 0.4],
        "source_type": "jira_issue",
        "source_id": "NXP-1",
        "title": "Test Doc",
        "created_at": NOW,
        "updated_at": NOW,
    }
    defaults.update(kwargs)
    return VectorChunk(**defaults)


@pytest.fixture
async def vs(tmp_path: Path) -> object:
    from nexuspkm.engine.vector_store import VectorStore

    store = VectorStore(db_path=str(tmp_path / "lancedb"), dimensions=4)
    await store._open()
    yield store
    await store.close()


class TestIntegrationStoreAndSearch:
    async def test_store_then_search_returns_top_result(self, vs: object) -> None:
        chunk = _make_chunk()
        await vs.store([chunk])  # type: ignore[attr-defined]
        results = await vs.search([0.1, 0.2, 0.3, 0.4], top_k=5)  # type: ignore[attr-defined]
        assert len(results) == 1
        assert results[0].chunk_id == "c1"
        assert results[0].document_id == "d1"

    async def test_store_then_delete_then_search_returns_empty(self, vs: object) -> None:
        chunk = _make_chunk()
        await vs.store([chunk])  # type: ignore[attr-defined]
        await vs.delete("d1")  # type: ignore[attr-defined]
        results = await vs.search([0.1, 0.2, 0.3, 0.4], top_k=5)  # type: ignore[attr-defined]
        assert results == []

    async def test_search_with_source_type_filter(self, vs: object) -> None:
        from nexuspkm.engine.vector_store import SearchFilters

        chunk_jira = _make_chunk("c1", "d1", source_type="jira_issue")
        chunk_obs = _make_chunk(
            "c2", "d2", source_type="obsidian_note", vector=[0.5, 0.6, 0.7, 0.8]
        )
        await vs.store([chunk_jira, chunk_obs])  # type: ignore[attr-defined]

        filters = SearchFilters(source_type="jira_issue")
        results = await vs.search([0.1, 0.2, 0.3, 0.4], top_k=5, filters=filters)  # type: ignore[attr-defined]
        assert all(r.source_type == "jira_issue" for r in results)
        assert len(results) == 1

    async def test_count_after_store_and_delete(self, vs: object) -> None:
        c1 = _make_chunk("c1", "d1")
        c2 = _make_chunk("c2", "d2", vector=[0.5, 0.6, 0.7, 0.8])
        await vs.store([c1, c2])  # type: ignore[attr-defined]
        assert await vs.count() == 2  # type: ignore[attr-defined]
        await vs.delete("d1")  # type: ignore[attr-defined]
        assert await vs.count() == 1  # type: ignore[attr-defined]

    async def test_store_is_idempotent_same_chunk_id_overwrites(self, vs: object) -> None:
        c1 = _make_chunk("c1", "d1", text="original")
        await vs.store([c1])  # type: ignore[attr-defined]
        assert await vs.count() == 1  # type: ignore[attr-defined]

        c1_updated = _make_chunk("c1", "d1", text="updated")
        await vs.store([c1_updated])  # type: ignore[attr-defined]
        assert await vs.count() == 1  # type: ignore[attr-defined]

        results = await vs.search([0.1, 0.2, 0.3, 0.4], top_k=1)  # type: ignore[attr-defined]
        assert results[0].text == "updated"

    async def test_search_score_is_in_valid_range(self, vs: object) -> None:
        chunk = _make_chunk()
        await vs.store([chunk])  # type: ignore[attr-defined]
        results = await vs.search([0.1, 0.2, 0.3, 0.4], top_k=5)  # type: ignore[attr-defined]
        assert len(results) == 1
        assert -1.0 <= results[0].score <= 1.0
