"""Integration tests for entity API endpoints.

Tests all 7 REST endpoints: entities CRUD, relationships, queue status,
contradictions list and resolve.
Spec: F-006 API endpoints
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nexuspkm.api.entities import get_contradiction_detector, get_extraction_queue, get_graph_store
from nexuspkm.engine.contradiction import ContradictionDetector
from nexuspkm.engine.extraction_queue import ExtractionQueue
from nexuspkm.engine.graph_store import GraphStore, PersonNode, ProjectNode
from nexuspkm.main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def graph_store(tmp_path: Path) -> Generator[GraphStore, None, None]:
    store = GraphStore(tmp_path / "kuzu")
    yield store
    store.close()


@pytest.fixture
def queue(tmp_path: Path) -> ExtractionQueue:
    q = ExtractionQueue(tmp_path / "queue.db")
    asyncio.run(q.init())
    return q


@pytest.fixture
def contradiction_detector(tmp_path: Path) -> ContradictionDetector:
    detector = ContradictionDetector(tmp_path / "contradictions.db")
    asyncio.run(detector.init())
    return detector


@pytest.fixture
def client(
    graph_store: GraphStore,
    queue: ExtractionQueue,
    contradiction_detector: ContradictionDetector,
) -> Generator[TestClient, None, None]:
    # Do NOT use context manager — keeps lifespan from running and overwriting overrides
    app.dependency_overrides[get_graph_store] = lambda: graph_store
    app.dependency_overrides[get_extraction_queue] = lambda: queue
    app.dependency_overrides[get_contradiction_detector] = lambda: contradiction_detector
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_graph_store, None)
        app.dependency_overrides.pop(get_extraction_queue, None)
        app.dependency_overrides.pop(get_contradiction_detector, None)


# ---------------------------------------------------------------------------
# GET /api/entities
# ---------------------------------------------------------------------------


def test_list_entities_empty(client: TestClient) -> None:
    response = client.get("/api/entities")
    assert response.status_code == 200
    assert response.json() == []


def test_list_entities_returns_persons(client: TestClient, graph_store: GraphStore) -> None:
    graph_store.upsert_person(PersonNode(id="p-1", name="Alice", email="alice@example.com"))
    graph_store.upsert_person(PersonNode(id="p-2", name="Bob", email="bob@example.com"))

    response = client.get("/api/entities")
    assert response.status_code == 200
    data = response.json()
    names = {item["name"] for item in data}
    assert "Alice" in names
    assert "Bob" in names


def test_list_entities_filter_by_type(client: TestClient, graph_store: GraphStore) -> None:
    graph_store.upsert_person(PersonNode(id="p-3", name="Charlie"))
    graph_store.upsert_project(ProjectNode(id="pr-1", name="Alpha Project"))

    response = client.get("/api/entities?type=person")
    assert response.status_code == 200
    data = response.json()
    assert all(item["entity_type"] == "person" for item in data)
    names = [item["name"] for item in data]
    assert "Charlie" in names
    assert "Alpha Project" not in names


def test_list_entities_filter_by_name(client: TestClient, graph_store: GraphStore) -> None:
    graph_store.upsert_person(PersonNode(id="p-4", name="Dave Jones"))
    graph_store.upsert_person(PersonNode(id="p-5", name="Eve Smith"))

    response = client.get("/api/entities?name=Jones")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Dave Jones"


# ---------------------------------------------------------------------------
# GET /api/entities/{id}
# ---------------------------------------------------------------------------


def test_get_entity_detail(client: TestClient, graph_store: GraphStore) -> None:
    graph_store.upsert_person(PersonNode(id="p-detail", name="Frank", email="frank@example.com"))

    response = client.get("/api/entities/p-detail")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "p-detail"
    assert data["name"] == "Frank"


def test_get_entity_not_found(client: TestClient) -> None:
    response = client.get("/api/entities/nonexistent-id")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/entities/merge
# ---------------------------------------------------------------------------


def test_merge_entities(client: TestClient, graph_store: GraphStore) -> None:
    graph_store.upsert_person(PersonNode(id="merge-src", name="John"))
    graph_store.upsert_person(PersonNode(id="merge-tgt", name="John Smith"))

    response = client.post(
        "/api/entities/merge",
        json={"source_id": "merge-src", "target_id": "merge-tgt"},
    )
    assert response.status_code == 200

    # Source should be removed, target should remain
    rows = graph_store.execute("MATCH (n:Person {id: 'merge-src'}) RETURN n.id")
    assert rows == []
    rows = graph_store.execute("MATCH (n:Person {id: 'merge-tgt'}) RETURN n.id")
    assert len(rows) == 1


def test_merge_entities_source_not_found(client: TestClient, graph_store: GraphStore) -> None:
    graph_store.upsert_person(PersonNode(id="merge-tgt2", name="Target"))

    response = client.post(
        "/api/entities/merge",
        json={"source_id": "nonexistent", "target_id": "merge-tgt2"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/relationships
# ---------------------------------------------------------------------------


def test_list_relationships_empty(client: TestClient) -> None:
    response = client.get("/api/relationships")
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# GET /api/extraction/status
# ---------------------------------------------------------------------------


def test_extraction_status(client: TestClient) -> None:
    response = client.get("/api/extraction/status")
    assert response.status_code == 200
    data = response.json()
    assert "pending" in data
    assert "processing" in data
    assert "done" in data
    assert "failed" in data
    assert data["pending"] == 0


# ---------------------------------------------------------------------------
# GET /api/contradictions
# ---------------------------------------------------------------------------


def test_list_contradictions_empty(client: TestClient) -> None:
    response = client.get("/api/contradictions")
    assert response.status_code == 200
    assert response.json() == []


def test_list_contradictions_returns_unresolved(
    client: TestClient, contradiction_detector: ContradictionDetector
) -> None:
    # Insert directly via SQL — schema already created by fixture's detector.init()
    conn = sqlite3.connect(contradiction_detector.db_path)
    conn.execute(
        "INSERT INTO contradictions VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "c-1",
            "entity-x",
            "status",
            "open",
            "closed",
            "doc-x",
            "2026-03-19T00:00:00+00:00",
            0,
            None,
            "status_conflict",
        ),
    )
    conn.commit()
    conn.close()

    response = client.get("/api/contradictions")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["entity_id"] == "entity-x"


# ---------------------------------------------------------------------------
# POST /api/contradictions/{id}/resolve
# ---------------------------------------------------------------------------


def test_resolve_contradiction(
    client: TestClient, contradiction_detector: ContradictionDetector
) -> None:
    # Insert directly via SQL — schema already created by fixture's detector.init()
    conn = sqlite3.connect(contradiction_detector.db_path)
    conn.execute(
        "INSERT INTO contradictions VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "c-resolve",
            "entity-y",
            "assignee_id",
            "alice",
            "bob",
            "doc-y",
            "2026-03-19T00:00:00+00:00",
            0,
            None,
            "assignment_conflict",
        ),
    )
    conn.commit()
    conn.close()

    response = client.post("/api/contradictions/c-resolve/resolve")
    assert response.status_code == 200

    conn = sqlite3.connect(contradiction_detector.db_path)
    row = conn.execute("SELECT resolved FROM contradictions WHERE id='c-resolve'").fetchone()
    conn.close()
    assert row[0] == 1


def test_resolve_contradiction_not_found(client: TestClient) -> None:
    response = client.post("/api/contradictions/nonexistent/resolve")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 503 when dependencies not configured
# ---------------------------------------------------------------------------


def test_extraction_status_503_when_not_configured() -> None:
    """Dependency not overridden → 503 Service Unavailable.

    TestClient is NOT used as a context manager intentionally — Starlette only
    runs the lifespan inside ``with TestClient(app)``. Without the context
    manager, the lifespan doesn't run and the default (503-raising) dependency
    remains active.
    """
    saved = dict(app.dependency_overrides)
    app.dependency_overrides.pop(get_extraction_queue, None)
    try:
        response = TestClient(app).get("/api/extraction/status")
        assert response.status_code == 503
    finally:
        app.dependency_overrides.update(saved)
