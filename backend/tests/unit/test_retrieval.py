"""Unit tests for HybridRetriever scoring and ranking logic.

All tests use mocked stores — no real DB I/O.
Spec: F-002 FR-5
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from nexuspkm.engine.retrieval import HybridRetriever, _compute_recency, _to_vector_filters
from nexuspkm.models.document import ChunkResult, SourceType
from nexuspkm.models.search import SearchFilters

NOW = datetime.datetime(2026, 3, 18, 12, 0, 0, tzinfo=datetime.UTC)
OLDER = datetime.datetime(2026, 3, 1, 0, 0, 0, tzinfo=datetime.UTC)


def _make_chunk(
    chunk_id: str = "c1",
    document_id: str = "d1",
    score: float = 0.8,
    created_at: datetime.datetime = NOW,
) -> ChunkResult:
    return ChunkResult(
        chunk_id=chunk_id,
        document_id=document_id,
        text="Sample text for testing purposes.",
        score=score,
        source_type=SourceType.JIRA_ISSUE,
        source_id="NXP-1",
        title="Test Doc",
        created_at=created_at,
    )


def _make_retriever() -> tuple[HybridRetriever, MagicMock, MagicMock, MagicMock]:
    vector_store = MagicMock()
    graph_store = MagicMock()
    embedding_provider = MagicMock()

    vector_store.search = AsyncMock()
    embedding_provider.embed_single = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])

    # Default: no graph connections
    graph_store.get_relationships = MagicMock(return_value=[])
    graph_store.get_topic = MagicMock(return_value=None)

    retriever = HybridRetriever(vector_store, graph_store, embedding_provider)
    return retriever, vector_store, graph_store, embedding_provider


class TestComputeRecency:
    def test_single_chunk_gets_full_recency(self) -> None:
        chunks = [_make_chunk()]
        recency = _compute_recency(chunks)
        assert recency["c1"] == 1.0

    def test_newest_gets_1_oldest_gets_0(self) -> None:
        new_chunk = _make_chunk("new", created_at=NOW)
        old_chunk = _make_chunk("old", created_at=OLDER)
        recency = _compute_recency([new_chunk, old_chunk])
        assert recency["new"] == pytest.approx(1.0)
        assert recency["old"] == pytest.approx(0.0)

    def test_same_timestamps_all_get_1(self) -> None:
        chunks = [_make_chunk("c1", created_at=NOW), _make_chunk("c2", created_at=NOW)]
        recency = _compute_recency(chunks)
        assert recency["c1"] == 1.0
        assert recency["c2"] == 1.0

    def test_empty_chunks_returns_empty(self) -> None:
        assert _compute_recency([]) == {}


class TestToVectorFilters:
    def test_none_filters_returns_none(self) -> None:
        assert _to_vector_filters(None) is None

    def test_empty_filters_returns_none(self) -> None:
        filters = SearchFilters()
        assert _to_vector_filters(filters) is None

    def test_single_source_type_passes_through(self) -> None:
        filters = SearchFilters(source_types=[SourceType.JIRA_ISSUE])
        result = _to_vector_filters(filters)
        assert result is not None
        assert result.source_type == SourceType.JIRA_ISSUE

    def test_multiple_source_types_omits_source_type(self) -> None:
        filters = SearchFilters(
            source_types=[SourceType.JIRA_ISSUE, SourceType.OBSIDIAN_NOTE],
            date_from=NOW,
        )
        result = _to_vector_filters(filters)
        assert result is not None
        assert result.source_type is None

    def test_date_range_passes_through(self) -> None:
        filters = SearchFilters(date_from=OLDER, date_to=NOW)
        result = _to_vector_filters(filters)
        assert result is not None
        assert result.date_from == OLDER
        assert result.date_to == NOW


class TestHybridRetrieverScoring:
    async def test_scoring_formula_no_graph_single_result(self) -> None:
        retriever, vector_store, _, _ = _make_retriever()
        chunk = _make_chunk(score=1.0)
        vector_store.search.return_value = [chunk]

        result = await retriever.retrieve("test query", top_k=10)

        assert len(result.chunks) == 1
        assert len(result.sources) == 1
        # combined = 0.6*1.0 + 0.3*0.0 + 0.1*1.0 = 0.7
        assert result.combined_score == pytest.approx(0.7)

    async def test_graph_boost_increases_score(self) -> None:
        retriever, vector_store, graph_store, _ = _make_retriever()
        chunk = _make_chunk(score=0.5)
        vector_store.search.return_value = [chunk]
        # 5 connections → full boost (1.0)
        graph_store.get_relationships = MagicMock(
            side_effect=lambda rel_type, from_id: (
                [{"from_id": from_id, "to_id": f"r{i}"} for i in range(5)]
                if rel_type == "RELATED_TO"
                else []
            )
        )

        result = await retriever.retrieve("test query", top_k=10)

        # combined = 0.6*0.5 + 0.3*1.0 + 0.1*1.0 = 0.3 + 0.3 + 0.1 = 0.7
        assert result.combined_score == pytest.approx(0.7)

    async def test_top_k_truncates_results(self) -> None:
        retriever, vector_store, _, _ = _make_retriever()
        # VectorStore returns 6 chunks (top_k*2 = 6 for top_k=3)
        chunks = [_make_chunk(f"c{i}", score=float(i) / 10) for i in range(6)]
        vector_store.search.return_value = chunks

        result = await retriever.retrieve("test query", top_k=3)

        assert len(result.chunks) <= 3

    async def test_deduplication_by_chunk_id(self) -> None:
        retriever, vector_store, _, _ = _make_retriever()
        # Two identical chunk_ids — should be deduplicated
        chunk = _make_chunk("c1")
        vector_store.search.return_value = [chunk, chunk]

        result = await retriever.retrieve("test query", top_k=10)

        ids = [c.chunk_id for c in result.chunks]
        assert ids.count("c1") == 1

    async def test_empty_vector_results_returns_empty_retrieval_result(self) -> None:
        retriever, vector_store, _, _ = _make_retriever()
        vector_store.search.return_value = []

        result = await retriever.retrieve("test query", top_k=10)

        assert result.chunks == []
        assert result.entities == []
        assert result.relationships == []
        assert result.combined_score == 0.0
        assert result.sources == []

    async def test_results_sorted_by_combined_score_descending(self) -> None:
        retriever, vector_store, _, _ = _make_retriever()
        # Give different scores — order should be deterministic after ranking
        chunks = [
            _make_chunk("c1", score=0.3, created_at=NOW),
            _make_chunk("c2", score=0.9, created_at=NOW),
            _make_chunk("c3", score=0.6, created_at=NOW),
        ]
        vector_store.search.return_value = chunks

        result = await retriever.retrieve("test query", top_k=10)

        scores = [s.relevance_score for s in result.sources]
        assert scores == sorted(scores, reverse=True)

    async def test_multi_source_type_filter_applied_post_search(self) -> None:
        retriever, vector_store, _, _ = _make_retriever()
        jira_chunk = _make_chunk("c1", document_id="d1")
        obsidian_chunk = ChunkResult(
            chunk_id="c2",
            document_id="d2",
            text="obsidian content here",
            score=0.8,
            source_type=SourceType.APPLE_NOTE,
            source_id="note-1",
            title="Apple Note",
            created_at=NOW,
        )
        vector_store.search.return_value = [jira_chunk, obsidian_chunk]

        filters = SearchFilters(source_types=[SourceType.JIRA_ISSUE, SourceType.OBSIDIAN_NOTE])
        result = await retriever.retrieve("test query", top_k=10, filters=filters)

        # APPLE_NOTE should be filtered out (not in filter list)
        result_types = {c.source_type for c in result.chunks}
        assert SourceType.APPLE_NOTE not in result_types

    async def test_combined_score_clamped_to_0_1(self) -> None:
        retriever, vector_store, _, _ = _make_retriever()
        # score > 1.0 (possible for non-normalised embeddings)
        chunk = _make_chunk(score=2.0)
        vector_store.search.return_value = [chunk]

        result = await retriever.retrieve("test query", top_k=10)

        assert 0.0 <= result.combined_score <= 1.0

    async def test_embed_single_failure_propagates_without_vector_search(self) -> None:
        retriever, vector_store, _, embedding_provider = _make_retriever()
        embedding_provider.embed_single = AsyncMock(side_effect=RuntimeError("quota exceeded"))

        with pytest.raises(RuntimeError, match="quota exceeded"):
            await retriever.retrieve("test query", top_k=5)

        # Vector store must not be called if embedding fails
        vector_store.search.assert_not_called()
