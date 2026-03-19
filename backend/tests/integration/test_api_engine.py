"""Integration tests for engine API endpoints.

Tests the /api/engine/* routes using TestClient with a mocked KnowledgeIndex.
Spec: F-002
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from nexuspkm.api.engine import get_knowledge_index
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
    index = MagicMock()
    index.insert = AsyncMock(return_value=_INDEXED_DOC)
    index.stats = AsyncMock(
        return_value={"documents": 5, "chunks": 20, "entities": 10, "relationships": 8}
    )
    return index


@pytest.fixture
def engine_client(mock_index: MagicMock) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_knowledge_index] = lambda: mock_index
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_knowledge_index, None)


def test_ingest_valid_document(engine_client: TestClient, mock_index: MagicMock) -> None:
    response = engine_client.post("/api/engine/ingest", json=_VALID_DOC_PAYLOAD)
    assert response.status_code == 200
    data = response.json()
    assert data["processing_status"] == ProcessingStatus.INDEXED
    mock_index.insert.assert_awaited_once()


def test_ingest_invalid_document(engine_client: TestClient) -> None:
    response = engine_client.post("/api/engine/ingest", json={"id": "", "content": ""})
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


def test_engine_unavailable_returns_503() -> None:
    # No dependency override — get_knowledge_index raises 503 by default
    client = TestClient(app)
    response = client.get("/api/engine/stats")
    assert response.status_code == 503
