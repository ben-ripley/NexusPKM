"""Unit tests for nexuspkm.engine.vector_store.

Uses injected _conn mock to avoid real LanceDB I/O.
Spec: F-002 FR-3
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pyarrow as pa
import pytest

from nexuspkm.models.document import SourceType

NOW = datetime.datetime(2026, 3, 18, 12, 0, 0, tzinfo=datetime.UTC)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_chunk(**kwargs: Any) -> Any:
    from nexuspkm.engine.vector_store import VectorChunk

    defaults: dict[str, Any] = {
        "chunk_id": "chunk-001",
        "document_id": "doc-001",
        "text": "Hello world",
        "vector": [0.1, 0.2, 0.3, 0.4],
        "source_type": "jira_issue",
        "source_id": "NXP-1",
        "title": "Test Doc",
        "created_at": NOW,
        "updated_at": NOW,
    }
    defaults.update(kwargs)
    return VectorChunk(**defaults)


def _make_arrow_result() -> pa.Table:
    return pa.table(
        {
            "chunk_id": ["chunk-001"],
            "document_id": ["doc-001"],
            "text": ["Hello world"],
            "vector": [[0.1, 0.2, 0.3, 0.4]],
            "source_type": ["jira_issue"],
            "source_id": ["NXP-1"],
            "title": ["Test Doc"],
            "created_at": pa.array([NOW], type=pa.timestamp("us", tz="UTC")),
            "_distance": [0.1],
        }
    )


def _make_mock_table(arrow_result: pa.Table | None = None) -> MagicMock:
    """Build a mock AsyncTable."""
    if arrow_result is None:
        arrow_result = _make_arrow_result()

    search_chain = MagicMock()
    search_chain.where = MagicMock(return_value=search_chain)
    search_chain.limit = MagicMock(return_value=search_chain)
    search_chain.to_arrow = AsyncMock(return_value=arrow_result)

    merge_builder = MagicMock()
    merge_builder.when_not_matched_insert_all = MagicMock(return_value=None)
    merge_builder.when_matched_update_all = MagicMock(return_value=None)
    merge_builder.execute = AsyncMock(return_value=None)

    mock_table = AsyncMock()
    mock_table.count_rows = AsyncMock(return_value=5)
    mock_table.delete = AsyncMock()
    mock_table.merge_insert = MagicMock(return_value=merge_builder)
    mock_table.vector_search = MagicMock(return_value=search_chain)
    # Expose search_chain so tests can assert on it via store._table._search_chain
    mock_table._search_chain = search_chain
    return mock_table


def _make_mock_conn(*, table_exists: bool = False) -> MagicMock:
    """Build a minimal mock AsyncConnection."""
    mock_table = _make_mock_table()

    mock_conn = AsyncMock()
    mock_conn.create_table = AsyncMock(return_value=mock_table)
    mock_conn.open_table = AsyncMock(return_value=mock_table)
    mock_conn.list_tables = AsyncMock(return_value=["documents"] if table_exists else [])
    mock_conn.close = AsyncMock()
    return mock_conn


@pytest.fixture
def mock_conn() -> MagicMock:
    return _make_mock_conn()


@pytest.fixture
async def store(mock_conn: MagicMock) -> Any:
    from nexuspkm.engine.vector_store import VectorStore

    vs = VectorStore(db_path="/tmp/test", dimensions=4, _conn=mock_conn)
    await vs._open()
    return vs


# ---------------------------------------------------------------------------
# VectorChunk model
# ---------------------------------------------------------------------------


class TestVectorChunk:
    def test_constructs_with_required_fields(self) -> None:
        chunk = _make_chunk()
        assert chunk.chunk_id == "chunk-001"
        assert chunk.document_id == "doc-001"
        assert chunk.text == "Hello world"
        assert chunk.source_type == "jira_issue"

    def test_vector_is_list_of_floats(self) -> None:
        chunk = _make_chunk(vector=[0.1, 0.2, 0.3, 0.4])
        assert isinstance(chunk.vector, list)
        assert all(isinstance(v, float) for v in chunk.vector)


# ---------------------------------------------------------------------------
# SearchFilters model
# ---------------------------------------------------------------------------


class TestSearchFilters:
    def test_defaults_are_all_none(self) -> None:
        from nexuspkm.engine.vector_store import SearchFilters

        f = SearchFilters()
        assert f.source_type is None
        assert f.date_from is None
        assert f.date_to is None

    def test_accepts_source_type(self) -> None:
        from nexuspkm.engine.vector_store import SearchFilters

        f = SearchFilters(source_type=SourceType.JIRA_ISSUE)
        assert f.source_type == SourceType.JIRA_ISSUE

    def test_accepts_date_range(self) -> None:
        from nexuspkm.engine.vector_store import SearchFilters

        f = SearchFilters(date_from=NOW, date_to=NOW)
        assert f.date_from == NOW
        assert f.date_to == NOW

    def test_rejects_inverted_date_range(self) -> None:
        from pydantic import ValidationError

        from nexuspkm.engine.vector_store import SearchFilters

        later = NOW + datetime.timedelta(days=1)
        with pytest.raises(ValidationError, match="date_from"):
            SearchFilters(date_from=later, date_to=NOW)


# ---------------------------------------------------------------------------
# VectorStore construction
# ---------------------------------------------------------------------------


class TestVectorStoreInit:
    def test_constructs_without_error(self, mock_conn: MagicMock) -> None:
        from nexuspkm.engine.vector_store import VectorStore

        vs = VectorStore(db_path="/tmp/test", dimensions=4, _conn=mock_conn)
        assert vs is not None


# ---------------------------------------------------------------------------
# _open() — lifecycle
# ---------------------------------------------------------------------------


class TestVectorStoreOpen:
    async def test_open_creates_table_when_not_exists(self, mock_conn: MagicMock) -> None:
        from nexuspkm.engine.vector_store import VectorStore

        vs = VectorStore(db_path="/tmp/test", dimensions=4, _conn=mock_conn)
        await vs._open()
        mock_conn.create_table.assert_called_once()
        mock_conn.open_table.assert_not_called()

    async def test_open_uses_open_table_when_table_exists(self) -> None:
        from nexuspkm.engine.vector_store import VectorStore

        conn = _make_mock_conn(table_exists=True)
        vs = VectorStore(db_path="/tmp/test", dimensions=4, _conn=conn)
        await vs._open()
        conn.open_table.assert_called_once_with("documents")
        conn.create_table.assert_not_called()

    async def test_open_is_idempotent_under_concurrent_calls(self, mock_conn: MagicMock) -> None:
        import asyncio

        from nexuspkm.engine.vector_store import VectorStore

        vs = VectorStore(db_path="/tmp/test", dimensions=4, _conn=mock_conn)
        # Fire two concurrent _open() calls — create_table must only be called once
        await asyncio.gather(vs._open(), vs._open())
        mock_conn.create_table.assert_called_once()


# ---------------------------------------------------------------------------
# store()
# ---------------------------------------------------------------------------


class TestVectorStoreStore:
    async def test_store_auto_opens_when_table_is_none(self, mock_conn: MagicMock) -> None:
        from nexuspkm.engine.vector_store import VectorStore

        vs = VectorStore(db_path="/tmp/test", dimensions=4, _conn=mock_conn)
        assert vs._table is None
        await vs.store([_make_chunk()])
        mock_conn.create_table.assert_called_once()

    async def test_store_empty_list_is_noop(self, store: Any) -> None:
        table = store._table
        await store.store([])
        table.merge_insert.assert_not_called()

    async def test_store_single_chunk_calls_merge_insert(self, store: Any) -> None:
        chunk = _make_chunk()
        await store.store([chunk])
        table = store._table
        table.merge_insert.assert_called_once_with("chunk_id")
        merge_builder = table.merge_insert.return_value
        merge_builder.when_not_matched_insert_all.assert_called_once()
        merge_builder.when_matched_update_all.assert_called_once()
        merge_builder.execute.assert_called_once()


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------


class TestVectorStoreSearch:
    async def test_search_auto_opens_when_table_is_none(self, mock_conn: MagicMock) -> None:
        from nexuspkm.engine.vector_store import VectorStore

        vs = VectorStore(db_path="/tmp/test", dimensions=4, _conn=mock_conn)
        assert vs._table is None
        await vs.search([0.1, 0.2, 0.3, 0.4], top_k=5)
        mock_conn.create_table.assert_called_once()

    async def test_search_returns_list_of_chunk_results(self, store: Any) -> None:
        from nexuspkm.models.document import ChunkResult

        results = await store.search([0.1, 0.2, 0.3, 0.4], top_k=5)
        assert isinstance(results, list)
        assert all(isinstance(r, ChunkResult) for r in results)

    async def test_search_converts_distance_to_score(self, store: Any) -> None:
        results = await store.search([0.1, 0.2, 0.3, 0.4], top_k=5)
        assert len(results) == 1
        # _distance=0.1 → score = 1.0 - 0.1 = 0.9
        assert abs(results[0].score - 0.9) < 1e-6

    async def test_search_passes_top_k(self, store: Any) -> None:
        await store.search([0.1, 0.2, 0.3, 0.4], top_k=3)
        store._table._search_chain.limit.assert_called_with(3)

    async def test_search_raises_on_nonpositive_top_k(self, store: Any) -> None:
        with pytest.raises(ValueError, match="top_k"):
            await store.search([0.1, 0.2, 0.3, 0.4], top_k=0)

    async def test_search_with_source_type_filter_calls_where(self, store: Any) -> None:
        from nexuspkm.engine.vector_store import SearchFilters

        filters = SearchFilters(source_type=SourceType.JIRA_ISSUE)
        await store.search([0.1, 0.2, 0.3, 0.4], top_k=5, filters=filters)
        chain = store._table._search_chain
        chain.where.assert_called()
        call_arg = chain.where.call_args[0][0]
        assert "source_type" in call_arg
        assert "jira_issue" in call_arg

    async def test_search_with_date_from_filter(self, store: Any) -> None:
        from nexuspkm.engine.vector_store import SearchFilters

        filters = SearchFilters(date_from=NOW)
        await store.search([0.1, 0.2, 0.3, 0.4], top_k=5, filters=filters)
        chain = store._table._search_chain
        chain.where.assert_called()
        call_arg = chain.where.call_args[0][0]
        assert "created_at" in call_arg
        assert "TIMESTAMP" in call_arg

    async def test_search_with_date_range_filter(self, store: Any) -> None:
        from nexuspkm.engine.vector_store import SearchFilters

        filters = SearchFilters(date_from=NOW, date_to=NOW)
        await store.search([0.1, 0.2, 0.3, 0.4], top_k=5, filters=filters)
        chain = store._table._search_chain
        chain.where.assert_called()
        call_arg = chain.where.call_args[0][0]
        assert "created_at" in call_arg
        assert "TIMESTAMP" in call_arg

    async def test_search_with_date_to_only_filter(self, store: Any) -> None:
        from nexuspkm.engine.vector_store import SearchFilters

        filters = SearchFilters(date_to=NOW)
        await store.search([0.1, 0.2, 0.3, 0.4], top_k=5, filters=filters)
        chain = store._table._search_chain
        chain.where.assert_called()
        call_arg = chain.where.call_args[0][0]
        assert "created_at" in call_arg

    async def test_search_with_all_filters_combined(self, store: Any) -> None:
        from nexuspkm.engine.vector_store import SearchFilters

        filters = SearchFilters(source_type=SourceType.JIRA_ISSUE, date_from=NOW, date_to=NOW)
        await store.search([0.1, 0.2, 0.3, 0.4], top_k=5, filters=filters)
        chain = store._table._search_chain
        chain.where.assert_called()
        call_arg = chain.where.call_args[0][0]
        assert "source_type" in call_arg
        assert "created_at" in call_arg

    async def test_search_no_filter_does_not_call_where(self, store: Any) -> None:
        await store.search([0.1, 0.2, 0.3, 0.4], top_k=5)
        store._table._search_chain.where.assert_not_called()

    async def test_search_raises_on_missing_distance_column(self, mock_conn: MagicMock) -> None:
        from nexuspkm.engine.vector_store import VectorStore

        # Return a result without _distance column
        bad_result = pa.table(
            {
                "chunk_id": ["c1"],
                "document_id": ["d1"],
                "text": ["hello"],
                "vector": [[0.1, 0.2, 0.3, 0.4]],
                "source_type": ["jira_issue"],
                "source_id": ["s1"],
                "title": ["t1"],
                "created_at": pa.array([NOW], type=pa.timestamp("us", tz="UTC")),
            }
        )
        mock_table = _make_mock_table(arrow_result=bad_result)
        mock_conn.create_table = AsyncMock(return_value=mock_table)

        vs = VectorStore(db_path="/tmp/test", dimensions=4, _conn=mock_conn)
        await vs._open()

        with pytest.raises(ValueError, match="_distance"):
            await vs.search([0.1, 0.2, 0.3, 0.4], top_k=5)


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------


class TestVectorStoreDelete:
    async def test_delete_auto_opens_when_table_is_none(self, mock_conn: MagicMock) -> None:
        from nexuspkm.engine.vector_store import VectorStore

        vs = VectorStore(db_path="/tmp/test", dimensions=4, _conn=mock_conn)
        assert vs._table is None
        await vs.delete("doc-001")
        mock_conn.create_table.assert_called_once()

    async def test_delete_calls_table_delete_with_document_id(self, store: Any) -> None:
        await store.delete("doc-001")
        store._table.delete.assert_called_once()
        call_arg = store._table.delete.call_args[0][0]
        assert "document_id" in call_arg
        assert "doc-001" in call_arg


# ---------------------------------------------------------------------------
# count()
# ---------------------------------------------------------------------------


class TestVectorStoreCount:
    async def test_count_auto_opens_when_table_is_none(self, mock_conn: MagicMock) -> None:
        from nexuspkm.engine.vector_store import VectorStore

        vs = VectorStore(db_path="/tmp/test", dimensions=4, _conn=mock_conn)
        assert vs._table is None
        result = await vs.count()
        mock_conn.create_table.assert_called_once()
        assert isinstance(result, int)

    async def test_count_returns_integer(self, store: Any) -> None:
        result = await store.count()
        assert isinstance(result, int)
        assert result == 5


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------


class TestVectorStoreClose:
    async def test_close_calls_conn_close(self, mock_conn: MagicMock) -> None:
        from nexuspkm.engine.vector_store import VectorStore

        vs = VectorStore(db_path="/tmp/test", dimensions=4, _conn=mock_conn)
        await vs._open()
        await vs.close()
        mock_conn.close.assert_called_once()
