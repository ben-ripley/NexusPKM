"""Unit tests for Obsidian Connector API endpoints.

Covers: api/obsidian.py
Spec: F-004 API endpoints
NXP-49
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexuspkm.api.obsidian import (
    get_connector_registry,
    get_sync_scheduler,
    router,
)
from nexuspkm.config.models import ObsidianConnectorConfig
from nexuspkm.connectors.base import ConnectorStatus
from nexuspkm.connectors.obsidian.connector import ObsidianNotesConnector
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
def connector(tmp_path: Path) -> ObsidianNotesConnector:
    vault = tmp_path / "vault"
    vault.mkdir()
    return ObsidianNotesConnector(
        vault_path=vault,
        state_dir=tmp_path / "state",
        config=ObsidianConnectorConfig(enabled=True, vault_path=vault),
    )


@pytest.fixture
def registry(connector: ObsidianNotesConnector) -> ConnectorRegistry:
    reg = ConnectorRegistry()
    reg.register(connector)
    reg.update_status(
        "obsidian",
        ConnectorStatus(name="obsidian", status="healthy", documents_synced=5),
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
    registry: ConnectorRegistry, scheduler: MagicMock, connector: ObsidianNotesConnector
) -> None:
    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.get("/api/connectors/obsidian/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["documents_synced"] == 5
    assert data["watcher_running"] is False
    assert "vault_path" in data


def test_get_status_404_when_not_configured(scheduler: MagicMock) -> None:
    empty_registry = ConnectorRegistry()
    app = _make_app(empty_registry, scheduler)
    client = TestClient(app)
    resp = client.get("/api/connectors/obsidian/status")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /sync
# ---------------------------------------------------------------------------


def test_post_sync_triggers_background_task(
    registry: ConnectorRegistry, scheduler: MagicMock
) -> None:
    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.post("/api/connectors/obsidian/sync")
    assert resp.status_code == 200
    assert resp.json()["status"] == "sync_started"


def test_post_sync_404_when_not_configured(scheduler: MagicMock) -> None:
    empty_registry = ConnectorRegistry()
    app = _make_app(empty_registry, scheduler)
    client = TestClient(app)
    resp = client.post("/api/connectors/obsidian/sync")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /config
# ---------------------------------------------------------------------------


def test_put_config_updates_interval(registry: ConnectorRegistry, scheduler: MagicMock) -> None:
    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.put("/api/connectors/obsidian/config", json={"sync_interval_minutes": 15})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"
    assert data["sync_interval_minutes"] == 15
    scheduler.reschedule_connector.assert_called_once_with("obsidian", 15 * 60)


def test_put_config_invalid_interval_rejected(
    registry: ConnectorRegistry, scheduler: MagicMock
) -> None:
    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.put("/api/connectors/obsidian/config", json={"sync_interval_minutes": 0})
    assert resp.status_code == 422


def test_put_config_404_when_not_configured(scheduler: MagicMock) -> None:
    empty_registry = ConnectorRegistry()
    app = _make_app(empty_registry, scheduler)
    client = TestClient(app)
    resp = client.put("/api/connectors/obsidian/config", json={"sync_interval_minutes": 10})
    assert resp.status_code == 404
