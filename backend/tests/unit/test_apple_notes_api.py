"""Unit tests for Apple Notes Connector API endpoints.

Covers: api/apple_notes.py
Spec: F-009 API endpoints
NXP-68
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexuspkm.api.apple_notes import (
    get_connector_registry,
    get_sync_scheduler,
    router,
)
from nexuspkm.config.models import AppleNotesConnectorConfig
from nexuspkm.connectors.apple_notes.connector import AppleNotesConnector
from nexuspkm.connectors.base import ConnectorStatus
from nexuspkm.connectors.registry import ConnectorRegistry
from nexuspkm.connectors.scheduler import SyncScheduler

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_app(registry: ConnectorRegistry, scheduler: SyncScheduler) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_connector_registry] = lambda: registry
    app.dependency_overrides[get_sync_scheduler] = lambda: scheduler
    return app


@pytest.fixture
def connector(tmp_path: Path) -> AppleNotesConnector:
    return AppleNotesConnector(
        state_dir=tmp_path / "state",
        config=AppleNotesConnectorConfig(enabled=True),
    )


@pytest.fixture
def registry(connector: AppleNotesConnector) -> ConnectorRegistry:
    reg = ConnectorRegistry()
    reg.register(connector)
    reg.update_status(
        "apple_notes",
        ConnectorStatus(name="apple_notes", status="healthy", documents_synced=10),
    )
    return reg


@pytest.fixture
def scheduler() -> MagicMock:
    sched = MagicMock(spec=SyncScheduler)
    sched.trigger_sync = AsyncMock()
    sched.reschedule_connector = MagicMock()
    return sched


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------


def test_get_status_healthy(
    registry: ConnectorRegistry,
    scheduler: MagicMock,
) -> None:
    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.get("/api/connectors/apple-notes/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["documents_synced"] == 10
    assert data["extraction_method"] == "applescript"
    assert "platform_supported" in data


def test_get_status_404_when_not_configured(scheduler: MagicMock) -> None:
    empty_registry = ConnectorRegistry()
    app = _make_app(empty_registry, scheduler)
    client = TestClient(app)
    resp = client.get("/api/connectors/apple-notes/status")
    assert resp.status_code == 404


def test_get_status_platform_supported_field(
    registry: ConnectorRegistry,
    scheduler: MagicMock,
) -> None:
    """platform_supported must be a boolean."""
    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.get("/api/connectors/apple-notes/status")
    assert isinstance(resp.json()["platform_supported"], bool)


# ---------------------------------------------------------------------------
# POST /sync
# ---------------------------------------------------------------------------


def test_post_sync_triggers_background_task(
    registry: ConnectorRegistry,
    scheduler: MagicMock,
) -> None:
    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.post("/api/connectors/apple-notes/sync")
    assert resp.status_code == 200
    assert resp.json()["status"] == "sync_started"


def test_post_sync_404_when_not_configured(scheduler: MagicMock) -> None:
    empty_registry = ConnectorRegistry()
    app = _make_app(empty_registry, scheduler)
    client = TestClient(app)
    resp = client.post("/api/connectors/apple-notes/sync")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /config
# ---------------------------------------------------------------------------


def test_put_config_updates_interval(
    registry: ConnectorRegistry,
    scheduler: MagicMock,
) -> None:
    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.put(
        "/api/connectors/apple-notes/config",
        json={"sync_interval_minutes": 30},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"
    assert data["sync_interval_minutes"] == 30
    scheduler.reschedule_connector.assert_called_once_with("apple_notes", 30 * 60)


def test_put_config_invalid_interval_rejected(
    registry: ConnectorRegistry,
    scheduler: MagicMock,
) -> None:
    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.put(
        "/api/connectors/apple-notes/config",
        json={"sync_interval_minutes": 0},
    )
    assert resp.status_code == 422


def test_put_config_over_max_rejected(
    registry: ConnectorRegistry,
    scheduler: MagicMock,
) -> None:
    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.put(
        "/api/connectors/apple-notes/config",
        json={"sync_interval_minutes": 9999},
    )
    assert resp.status_code == 422


def test_put_config_404_when_not_configured(scheduler: MagicMock) -> None:
    empty_registry = ConnectorRegistry()
    app = _make_app(empty_registry, scheduler)
    client = TestClient(app)
    resp = client.put(
        "/api/connectors/apple-notes/config",
        json={"sync_interval_minutes": 10},
    )
    assert resp.status_code == 404
