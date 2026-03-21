"""Unit tests for JIRA Connector API endpoints.

Covers: api/jira.py
Spec: F-011 API endpoints
NXP-85
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexuspkm.api.jira import (
    get_connector_registry,
    get_sync_scheduler,
    router,
)
from nexuspkm.config.models import JiraConnectorConfig
from nexuspkm.connectors.base import ConnectorStatus
from nexuspkm.connectors.jira.connector import JiraConnector
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
def connector(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JiraConnector:
    monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "token123")
    return JiraConnector(
        state_dir=tmp_path / "state",
        config=JiraConnectorConfig(
            enabled=True,
            base_url="https://example.atlassian.net",
            jql_filter="project = NXP",
        ),
    )


@pytest.fixture
def registry(connector: JiraConnector) -> ConnectorRegistry:
    reg = ConnectorRegistry()
    reg.register(connector)
    reg.update_status(
        "jira",
        ConnectorStatus(name="jira", status="healthy", documents_synced=42),
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
    resp = client.get("/api/connectors/jira/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["documents_synced"] == 42
    assert data["base_url"] == "https://example.atlassian.net"
    assert data["jql_filter"] == "project = NXP"


def test_get_status_404_when_not_configured(scheduler: MagicMock) -> None:
    empty_registry = ConnectorRegistry()
    app = _make_app(empty_registry, scheduler)
    client = TestClient(app)
    resp = client.get("/api/connectors/jira/status")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /sync
# ---------------------------------------------------------------------------


def test_post_sync_triggers_background_task(
    registry: ConnectorRegistry,
    scheduler: MagicMock,
) -> None:
    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.post("/api/connectors/jira/sync")
    assert resp.status_code == 200
    assert resp.json()["status"] == "sync_started"


def test_post_sync_404_when_not_configured(scheduler: MagicMock) -> None:
    empty_registry = ConnectorRegistry()
    app = _make_app(empty_registry, scheduler)
    client = TestClient(app)
    resp = client.post("/api/connectors/jira/sync")
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
    resp = client.put("/api/connectors/jira/config", json={"sync_interval_minutes": 60})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"
    assert data["sync_interval_minutes"] == 60
    scheduler.reschedule_connector.assert_called_once_with("jira", 60 * 60)


def test_put_config_invalid_interval_rejected(
    registry: ConnectorRegistry,
    scheduler: MagicMock,
) -> None:
    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.put("/api/connectors/jira/config", json={"sync_interval_minutes": 0})
    assert resp.status_code == 422


def test_put_config_over_max_rejected(
    registry: ConnectorRegistry,
    scheduler: MagicMock,
) -> None:
    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.put("/api/connectors/jira/config", json={"sync_interval_minutes": 9999})
    assert resp.status_code == 422


def test_put_config_404_when_not_configured(scheduler: MagicMock) -> None:
    empty_registry = ConnectorRegistry()
    app = _make_app(empty_registry, scheduler)
    client = TestClient(app)
    resp = client.put("/api/connectors/jira/config", json={"sync_interval_minutes": 15})
    assert resp.status_code == 404


def test_put_config_rolls_back_on_scheduler_error(
    connector: JiraConnector,
    registry: ConnectorRegistry,
    scheduler: MagicMock,
) -> None:
    scheduler.reschedule_connector.side_effect = RuntimeError("scheduler error")
    original_interval = connector.sync_interval_minutes

    app = _make_app(registry, scheduler)
    client = TestClient(app)
    resp = client.put("/api/connectors/jira/config", json={"sync_interval_minutes": 120})

    assert resp.status_code == 500
    assert connector.sync_interval_minutes == original_interval
