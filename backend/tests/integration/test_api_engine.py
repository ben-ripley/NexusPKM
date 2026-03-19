"""Integration tests for engine API endpoints.

Tests the /api/engine/* routes using TestClient with a mocked KnowledgeIndex.
Spec: F-002
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from nexuspkm.api.engine import get_knowledge_index
from nexuspkm.engine.index import KnowledgeIndex
from nexuspkm.main import app
from nexuspkm.models.document import Document, ProcessingStatus

_NOW = "2026-03-18T12:00:00+00:00"

_VALID_DOC_PAYLOAD: dict[str, object] = {
    "id": "doc-1",
    "content": "Test content for indexing",
    "metadata": {
        "source_type": "obsidian_note",
        "source_id": "note-1",
        "title": "Test Note",
        "created_at": _NOW,
        "updated_at": _NOW,
        "synced_at": _NOW,
    },
}

_INDEXED_DOC = Document.model_validate(
    {**_VALID_DOC_PAYLOAD, "processing_status": ProcessingStatus.INDEXED}
)


@pytest.fixture
def mock_index() -> MagicMock:
    index = MagicMock(spec=KnowledgeIndex)
    index.insert = AsyncMock(return_value=_INDEXED_DOC)
    index.stats = AsyncMock(
        return_value={"documents": 5, "chunks": 20, "entities": 10, "relationships": 8}
    )
    return index


@pytest.fixture
def engine_client(mock_index: MagicMock) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_knowledge_index] = lambda: mock_index
    try:
        # TestClient is NOT used as a context manager here intentionally.
        # Starlette 0.52 only runs the lifespan inside `with TestClient(app)`.
        # Without the context manager, the lifespan doesn't run and our
        # dependency override is not overwritten by the real initialisation.
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_knowledge_index, None)


def test_ingest_valid_document(engine_client: TestClient, mock_index: MagicMock) -> None:
    response = engine_client.post("/api/engine/ingest", json=_VALID_DOC_PAYLOAD)
    assert response.status_code == 200
    data = response.json()
    assert data["processing_status"] == ProcessingStatus.INDEXED.value
    mock_index.insert.assert_awaited_once()


def test_ingest_invalid_document(engine_client: TestClient) -> None:
    # Missing required `metadata` field — unambiguously invalid regardless of validators
    response = engine_client.post("/api/engine/ingest", json={"id": "doc-1", "content": "text"})
    assert response.status_code == 422


def test_ingest_propagates_engine_error(engine_client: TestClient, mock_index: MagicMock) -> None:
    mock_index.insert = AsyncMock(side_effect=RuntimeError("store unavailable"))
    response = engine_client.post("/api/engine/ingest", json=_VALID_DOC_PAYLOAD)
    assert response.status_code == 500


def test_stats_returns_counts(engine_client: TestClient) -> None:
    response = engine_client.get("/api/engine/stats")
    assert response.status_code == 200
    data = response.json()
    assert data == {"documents": 5, "chunks": 20, "entities": 10, "relationships": 8}


def test_status_returns_idle(engine_client: TestClient) -> None:
    response = engine_client.get("/api/engine/status")
    assert response.status_code == 200
    assert response.json() == {"status": "idle", "queue_size": 0}


def test_reindex_returns_completed(engine_client: TestClient) -> None:
    response = engine_client.post("/api/engine/reindex", json={"full": False})
    assert response.status_code == 200
    assert response.json() == {"status": "completed", "reindexed": 0}


def test_reindex_full_flag_accepted(engine_client: TestClient) -> None:
    # Stub returns the same response regardless of full flag until NXP-5x is implemented.
    # This test ensures the flag is accepted and doesn't raise a validation error.
    response = engine_client.post("/api/engine/reindex", json={"full": True})
    assert response.status_code == 200
    assert response.json() == {"status": "completed", "reindexed": 0}


def test_get_knowledge_index_raises_503_by_default() -> None:
    """The sentinel dependency raises 503 when not overridden by lifespan."""
    with pytest.raises(HTTPException) as exc_info:
        get_knowledge_index()
    assert exc_info.value.status_code == 503


def test_engine_unavailable_returns_503() -> None:
    # Explicitly clear any override to guarantee the sentinel is active,
    # then make a GET and a POST request to verify both methods propagate 503.
    saved = app.dependency_overrides.pop(get_knowledge_index, None)
    try:
        client = TestClient(app)
        assert client.get("/api/engine/stats").status_code == 503
        assert client.post("/api/engine/ingest", json=_VALID_DOC_PAYLOAD).status_code == 503
    finally:
        if saved is not None:
            app.dependency_overrides[get_knowledge_index] = saved
