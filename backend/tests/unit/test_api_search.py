"""Unit tests for search API endpoints.

Tests POST /api/search, GET /api/search/suggest, GET /api/search/facets.
Spec: F-007
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from nexuspkm.api.engine import get_knowledge_index
from nexuspkm.api.search import get_graph_store as search_get_graph_store
from nexuspkm.api.search import get_obsidian_vault_path as search_get_obsidian_vault_path
from nexuspkm.engine.graph_store import GraphStore
from nexuspkm.engine.index import KnowledgeIndex
from nexuspkm.main import app
from nexuspkm.models.document import (
    ChunkResult,
    EntityResult,
    RetrievalResult,
    SourceAttribution,
)

_NOW = "2026-03-18T12:00:00+00:00"
_NOW2 = "2026-02-15T09:00:00+00:00"


def _make_chunk(
    chunk_id: str = "c-1",
    document_id: str = "doc-1",
    source_type: str = "obsidian_note",
    created_at: str = _NOW,
) -> ChunkResult:
    return ChunkResult.model_validate(
        {
            "chunk_id": chunk_id,
            "document_id": document_id,
            "text": "some chunk text",
            "score": 0.8,
            "source_type": source_type,
            "source_id": "src-1",
            "title": "Test Doc",
            "created_at": created_at,
        }
    )


def _make_source(
    document_id: str = "doc-1",
    source_type: str = "obsidian_note",
    created_at: str = _NOW,
) -> SourceAttribution:
    return SourceAttribution.model_validate(
        {
            "document_id": document_id,
            "title": "Test Doc",
            "source_type": source_type,
            "source_id": "src-1",
            "excerpt": "excerpt text",
            "relevance_score": 0.85,
            "created_at": created_at,
        }
    )


def _make_retrieval_result(
    chunks: list[ChunkResult] | None = None,
    sources: list[SourceAttribution] | None = None,
    entities: list[EntityResult] | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        chunks=chunks or [],
        entities=entities or [],
        relationships=[],
        combined_score=0.8,
        sources=sources or [],
    )


@pytest.fixture
def mock_index() -> MagicMock:
    index = MagicMock(spec=KnowledgeIndex)
    index.retrieve = AsyncMock(return_value=_make_retrieval_result())
    return index


@pytest.fixture
def mock_graph() -> MagicMock:
    return MagicMock(spec=GraphStore)


@pytest.fixture
def client(mock_index: MagicMock, mock_graph: MagicMock) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_knowledge_index] = lambda: mock_index
    app.dependency_overrides[search_get_graph_store] = lambda: mock_graph
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_knowledge_index, None)
        app.dependency_overrides.pop(search_get_graph_store, None)


# ---------------------------------------------------------------------------
# POST /api/search — validation
# ---------------------------------------------------------------------------


def test_search_empty_query_returns_422(client: TestClient) -> None:
    response = client.post("/api/search", json={"query": ""})
    assert response.status_code == 422


def test_search_missing_query_returns_422(client: TestClient) -> None:
    response = client.post("/api/search", json={})
    assert response.status_code == 422


def test_search_date_from_after_date_to_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/search",
        json={
            "query": "test",
            "filters": {
                "date_from": "2026-03-20T00:00:00+00:00",
                "date_to": "2026-03-01T00:00:00+00:00",
            },
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/search — valid responses
# ---------------------------------------------------------------------------


def test_search_valid_returns_200(client: TestClient) -> None:
    response = client.post("/api/search", json={"query": "meeting notes"})
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "total_count" in data
    assert "facets" in data


def test_search_response_has_facets_shape(client: TestClient) -> None:
    response = client.post("/api/search", json={"query": "test"})
    assert response.status_code == 200
    facets = response.json()["facets"]
    assert "source_types" in facets
    assert "date_histogram" in facets
    assert "top_entities" in facets
    assert "top_tags" in facets


def test_search_facet_source_type_counts_match_chunks(
    client: TestClient, mock_index: MagicMock
) -> None:
    mock_index.retrieve = AsyncMock(
        return_value=_make_retrieval_result(
            chunks=[
                _make_chunk(chunk_id="c-1", source_type="obsidian_note"),
                _make_chunk(chunk_id="c-2", source_type="obsidian_note"),
                _make_chunk(chunk_id="c-3", source_type="teams_transcript"),
            ],
            sources=[_make_source(document_id="doc-1", source_type="obsidian_note")],
        )
    )
    response = client.post("/api/search", json={"query": "test"})
    assert response.status_code == 200
    source_types = response.json()["facets"]["source_types"]
    assert source_types.get("obsidian_note") == 2
    assert source_types.get("teams_transcript") == 1


def test_search_date_histogram_groups_by_month(client: TestClient, mock_index: MagicMock) -> None:
    mock_index.retrieve = AsyncMock(
        return_value=_make_retrieval_result(
            chunks=[
                _make_chunk(chunk_id="c-1", created_at=_NOW),  # March 2026
                _make_chunk(chunk_id="c-2", created_at=_NOW),  # March 2026
                _make_chunk(chunk_id="c-3", created_at=_NOW2),  # Feb 2026
            ],
        )
    )
    response = client.post("/api/search", json={"query": "test"})
    assert response.status_code == 200
    histogram = response.json()["facets"]["date_histogram"]
    assert len(histogram) == 2
    counts = {b["count"] for b in histogram}
    assert 2 in counts
    assert 1 in counts


def test_search_empty_retrieval_returns_200_not_500(
    client: TestClient, mock_index: MagicMock
) -> None:
    mock_index.retrieve = AsyncMock(return_value=_make_retrieval_result())
    response = client.post("/api/search", json={"query": "unknown xyz"})
    assert response.status_code == 200
    data = response.json()
    assert data["results"] == []
    assert data["total_count"] == 0


def test_search_maps_sources_to_results(client: TestClient, mock_index: MagicMock) -> None:
    source = _make_source(document_id="doc-42", source_type="jira_issue")
    mock_index.retrieve = AsyncMock(return_value=_make_retrieval_result(sources=[source]))
    response = client.post("/api/search", json={"query": "test"})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["id"] == "doc-42"
    assert results[0]["source_type"] == "jira_issue"


def test_search_503_when_index_unavailable() -> None:
    saved = dict(app.dependency_overrides)
    app.dependency_overrides.pop(get_knowledge_index, None)
    try:
        response = TestClient(app).post("/api/search", json={"query": "test"})
        assert response.status_code == 503
    finally:
        app.dependency_overrides.update(saved)


# ---------------------------------------------------------------------------
# GET /api/search/suggest
# ---------------------------------------------------------------------------


def test_suggest_returns_200_list(client: TestClient, mock_graph: MagicMock) -> None:
    mock_graph.execute = MagicMock(
        return_value=[{"name": "Project Alpha"}, {"name": "Project Beta"}]
    )
    response = client.get("/api/search/suggest?q=pro")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_suggest_missing_q_returns_422(client: TestClient) -> None:
    response = client.get("/api/search/suggest")
    assert response.status_code == 422


def test_suggest_returns_empty_list_when_graph_raises(
    client: TestClient, mock_graph: MagicMock
) -> None:
    mock_graph.execute = MagicMock(side_effect=RuntimeError("graph unavailable"))
    response = client.get("/api/search/suggest?q=test")
    assert response.status_code == 200
    assert response.json() == []


def test_suggest_deduplicates_names(client: TestClient, mock_graph: MagicMock) -> None:
    # Same name returned from multiple tables — should deduplicate
    mock_graph.execute = MagicMock(
        side_effect=[
            [{"name": "Alpha"}],
            [{"name": "Alpha"}],
            [],
        ]
    )
    response = client.get("/api/search/suggest?q=al")
    assert response.status_code == 200
    data = response.json()
    assert data.count("Alpha") == 1


def test_search_obsidian_url_reconstructed_from_vault_path(
    client: TestClient, mock_index: MagicMock
) -> None:
    """URL should be built from vault_path + source_id for obsidian_note sources."""
    vault = Path("/Users/test/vault")
    source = SourceAttribution.model_validate(
        {
            "document_id": "doc-obs",
            "title": "My Note",
            "source_type": "obsidian_note",
            "source_id": "folder/note.md",
            "excerpt": "some text",
            "relevance_score": 0.7,
            "created_at": _NOW,
        }
    )
    mock_index.retrieve = AsyncMock(return_value=_make_retrieval_result(sources=[source]))
    app.dependency_overrides[search_get_obsidian_vault_path] = lambda: vault
    try:
        response = client.post("/api/search", json={"query": "test"})
    finally:
        app.dependency_overrides.pop(search_get_obsidian_vault_path, None)

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["url"] is not None
    assert result["url"].startswith("obsidian://open?path=")
    assert "folder" in result["url"]
    assert "note.md" in result["url"]


def test_search_obsidian_url_none_when_no_vault_path(
    client: TestClient, mock_index: MagicMock
) -> None:
    """URL should be None when no vault path is configured."""
    source = SourceAttribution.model_validate(
        {
            "document_id": "doc-obs",
            "title": "My Note",
            "source_type": "obsidian_note",
            "source_id": "folder/note.md",
            "excerpt": "some text",
            "relevance_score": 0.7,
            "created_at": _NOW,
        }
    )
    mock_index.retrieve = AsyncMock(return_value=_make_retrieval_result(sources=[source]))
    response = client.post("/api/search", json={"query": "test"})
    assert response.status_code == 200
    assert response.json()["results"][0]["url"] is None


# ---------------------------------------------------------------------------
# GET /api/search/facets
# ---------------------------------------------------------------------------


def test_facets_returns_200(client: TestClient) -> None:
    response = client.get("/api/search/facets")
    assert response.status_code == 200


def test_facets_returns_source_types_list(client: TestClient) -> None:
    response = client.get("/api/search/facets")
    data = response.json()
    assert "source_types" in data
    assert isinstance(data["source_types"], list)
    assert len(data["source_types"]) > 0
