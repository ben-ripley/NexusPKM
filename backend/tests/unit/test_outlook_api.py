"""Unit tests for Outlook Connector API endpoints.

Covers: api/outlook.py
Spec: F-010 API endpoints
NXP-69
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexuspkm.api.outlook import (
    get_connector_registry,
    get_sync_scheduler,
    router,
)
from nexuspkm.config.models import OutlookConnectorConfig
from nexuspkm.connectors.base import ConnectorStatus
from nexuspkm.connectors.ms_graph.outlook import OutlookConnector
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
def connector(tmp_path: Path) -> OutlookConnector:
    return OutlookConnector(
        token_dir=tmp_path / "tokens",
        state_dir=tmp_path / "state",
        config=OutlookConnectorConfig(enabled=True),
    )


@pytest.fixture
def registry(connector: OutlookConnector) -> ConnectorRegistry:
    reg = ConnectorRegistry()
    reg.register(connector)
    reg.update_status(
        "outlook",
        ConnectorStatus(name="outlook", status="healthy", documents_synced=5),
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
    resp = client.get("/api/connectors/outlook/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["documents_synced"] == 5
    assert data["name"] == "outlook"
    assert "folders" in data
    assert "calendar_window_days" in data


def test_get_status_404_when_not_configured(scheduler: MagicMock) -> None:
    empty_registry = ConnectorRegistry()
    app = _make_app(empty_registry, scheduler)
    client = TestClient(app)
    resp = client.get("/api/connectors/outlook/status")
    assert resp.status_code == 404


def test_get_status_includes_folders(
    connector: OutlookConnector,
    scheduler: MagicMock,
) -> None:
    connector.update_config(folders=["Inbox", "Archive"])
    reg = ConnectorRegistry()
    reg.register(connector)
    reg.update_status("outlook", ConnectorStatus(name="outlook", status="healthy"))
    app = _make_app(reg, scheduler)
    client = TestClient(app)
    resp = client.get("/api/connectors/outlook/status")
    assert resp.status_code == 200
    assert resp.json()["folders"] == ["Inbox", "Archive"]


# ---------------------------------------------------------------------------
# POST /sync
# ---------------------------------------------------------------------------


def test_post_sync_triggers_background_task(
    registry: ConnectorRegistry,
    scheduler: MagicMock,
) -> None:
    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.post("/api/connectors/outlook/sync")
    assert resp.status_code == 200
    assert resp.json()["status"] == "sync_started"


def test_post_sync_404_when_not_configured(scheduler: MagicMock) -> None:
    empty_registry = ConnectorRegistry()
    app = _make_app(empty_registry, scheduler)
    client = TestClient(app)
    resp = client.post("/api/connectors/outlook/sync")
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
        "/api/connectors/outlook/config",
        json={"sync_interval_minutes": 30},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"
    assert data["sync_interval_minutes"] == 30
    scheduler.reschedule_connector.assert_called_once_with("outlook", 30 * 60)


def test_put_config_updates_folders(
    connector: OutlookConnector,
    registry: ConnectorRegistry,
    scheduler: MagicMock,
) -> None:
    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.put(
        "/api/connectors/outlook/config",
        json={"folders": ["Archive", "Inbox"]},
    )
    assert resp.status_code == 200
    assert connector.config.folders == ["Archive", "Inbox"]


def test_put_config_updates_sender_domains(
    connector: OutlookConnector,
    registry: ConnectorRegistry,
    scheduler: MagicMock,
) -> None:
    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.put(
        "/api/connectors/outlook/config",
        json={"sender_domains": ["example.com", "acme.com"]},
    )
    assert resp.status_code == 200
    assert connector.config.sender_domains == ["example.com", "acme.com"]


def test_put_config_invalid_interval_rejected(
    registry: ConnectorRegistry,
    scheduler: MagicMock,
) -> None:
    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.put(
        "/api/connectors/outlook/config",
        json={"sync_interval_minutes": 0},
    )
    assert resp.status_code == 422


def test_put_config_404_when_not_configured(scheduler: MagicMock) -> None:
    empty_registry = ConnectorRegistry()
    app = _make_app(empty_registry, scheduler)
    client = TestClient(app)
    resp = client.put(
        "/api/connectors/outlook/config",
        json={"sync_interval_minutes": 10},
    )
    assert resp.status_code == 404


def test_put_config_rolls_back_interval_on_scheduler_error(
    connector: OutlookConnector,
    registry: ConnectorRegistry,
    scheduler: MagicMock,
) -> None:
    """If reschedule_connector raises, the connector's interval is reverted."""
    scheduler.reschedule_connector.side_effect = RuntimeError("scheduler unavailable")
    original_interval = connector.config.sync_interval_minutes

    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.put(
        "/api/connectors/outlook/config",
        json={"sync_interval_minutes": 60},
    )

    assert resp.status_code == 500
    assert connector.config.sync_interval_minutes == original_interval


def test_put_config_rolls_back_all_fields_on_scheduler_error(
    connector: OutlookConnector,
    registry: ConnectorRegistry,
    scheduler: MagicMock,
) -> None:
    """Combined payload: interval + folders both rolled back when reschedule fails."""
    scheduler.reschedule_connector.side_effect = RuntimeError("scheduler unavailable")
    original_interval = connector.config.sync_interval_minutes
    original_folders = connector.config.folders[:]

    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.put(
        "/api/connectors/outlook/config",
        json={"sync_interval_minutes": 60, "folders": ["Archive"]},
    )

    assert resp.status_code == 500
    # Both interval and folders must be reverted
    assert connector.config.sync_interval_minutes == original_interval
    assert connector.config.folders == original_folders


def test_put_config_no_interval_does_not_reschedule(
    registry: ConnectorRegistry,
    scheduler: MagicMock,
) -> None:
    """PUT /config with no sync_interval_minutes does not call reschedule_connector."""
    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.put(
        "/api/connectors/outlook/config",
        json={"calendar_window_days": 60},
    )
    assert resp.status_code == 200
    scheduler.reschedule_connector.assert_not_called()
