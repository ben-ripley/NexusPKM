"""Unit tests for dashboard API endpoints.

Tests GET /api/dashboard/activity, /api/dashboard/stats, /api/dashboard/upcoming.
Spec: F-008
NXP-65
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from nexuspkm.api.engine import get_knowledge_index
from nexuspkm.engine.index import KnowledgeIndex
from nexuspkm.main import app


@pytest.fixture
def mock_index() -> MagicMock:
    index = MagicMock(spec=KnowledgeIndex)
    index.stats = AsyncMock(
        return_value={
            "documents": 42,
            "chunks": 210,
            "entities": 15,
            "relationships": 8,
        }
    )
    return index


@pytest.fixture
def client(mock_index: MagicMock) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_knowledge_index] = lambda: mock_index
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_knowledge_index, None)


# ---------------------------------------------------------------------------
# GET /api/dashboard/activity
# ---------------------------------------------------------------------------


def test_activity_returns_200_with_empty_list(client: TestClient) -> None:
    response = client.get("/api/dashboard/activity")
    assert response.status_code == 200
    data = response.json()
    assert data == {"items": []}


# ---------------------------------------------------------------------------
# GET /api/dashboard/stats
# ---------------------------------------------------------------------------


def test_stats_returns_200_with_correct_fields(client: TestClient) -> None:
    response = client.get("/api/dashboard/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_documents"] == 42
    assert data["total_chunks"] == 210
    assert data["total_entities"] == 15
    assert data["total_relationships"] == 8
    assert data["by_source_type"] == {}


def test_stats_503_when_index_unavailable() -> None:
    saved = dict(app.dependency_overrides)
    app.dependency_overrides.pop(get_knowledge_index, None)
    try:
        response = TestClient(app).get("/api/dashboard/stats")
        assert response.status_code == 503
    finally:
        app.dependency_overrides.update(saved)


# ---------------------------------------------------------------------------
# GET /api/dashboard/upcoming
# ---------------------------------------------------------------------------


def test_upcoming_returns_200_with_empty_list(client: TestClient) -> None:
    response = client.get("/api/dashboard/upcoming")
    assert response.status_code == 200
    data = response.json()
    assert data == {"items": []}
