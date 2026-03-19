"""Unit tests for Teams Connector API endpoints.

Covers: api/connectors.py
Spec refs: F-003 API endpoints
NXP-56
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexuspkm.api.connectors import (
    get_connector_registry,
    get_sync_scheduler,
    router,
)
from nexuspkm.config.models import TeamsConnectorConfig
from nexuspkm.connectors.base import ConnectorStatus
from nexuspkm.connectors.ms_graph.auth import AuthFlowContext, DeviceCodeInfo
from nexuspkm.connectors.ms_graph.teams import TeamsTranscriptConnector
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
def connector(tmp_path: Path) -> TeamsTranscriptConnector:
    return TeamsTranscriptConnector(
        token_dir=tmp_path / "tokens",
        state_dir=tmp_path / "state",
        config=TeamsConnectorConfig(),
    )


@pytest.fixture
def registry(connector: TeamsTranscriptConnector) -> ConnectorRegistry:
    reg = ConnectorRegistry()
    reg.register(connector)
    reg.update_status(
        "teams",
        ConnectorStatus(name="teams", status="healthy", documents_synced=5),
    )
    return reg


@pytest.fixture
def scheduler() -> MagicMock:
    return MagicMock(spec=SyncScheduler)


@pytest.fixture
def client(registry: ConnectorRegistry, scheduler: MagicMock) -> TestClient:
    app = _make_app(registry, scheduler)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# POST /authenticate
# ---------------------------------------------------------------------------


class TestAuthenticate:
    def test_returns_device_code_info(
        self,
        client: TestClient,
        connector: TeamsTranscriptConnector,
    ) -> None:
        info = DeviceCodeInfo(
            user_code="ABCD-1234",
            verification_uri="https://microsoft.com/devicelogin",
            expires_in=900,
            message="Go to https://microsoft.com/devicelogin and enter ABCD-1234",
        )
        context = MagicMock(spec=AuthFlowContext)

        with (
            patch.object(
                connector,
                "initiate_auth_flow",
                new=AsyncMock(return_value=(info, context)),
            ),
            patch.object(
                connector,
                "complete_auth_flow",
                new=AsyncMock(return_value=True),
            ),
        ):
            response = client.post("/api/connectors/teams/authenticate")

        assert response.status_code == 200
        data = response.json()
        assert data["user_code"] == "ABCD-1234"
        assert data["verification_uri"] == "https://microsoft.com/devicelogin"
        assert data["expires_in"] == 900

    def test_returns_404_when_connector_not_registered(self, scheduler: MagicMock) -> None:
        empty_registry = ConnectorRegistry()
        app = _make_app(empty_registry, scheduler)
        c = TestClient(app, raise_server_exceptions=False)
        response = c.post("/api/connectors/teams/authenticate")
        assert response.status_code == 404

    def test_returns_500_when_auth_raises(
        self,
        client: TestClient,
        connector: TeamsTranscriptConnector,
    ) -> None:
        with patch.object(
            connector,
            "initiate_auth_flow",
            new=AsyncMock(side_effect=RuntimeError("tenant not configured")),
        ):
            response = client.post("/api/connectors/teams/authenticate")

        assert response.status_code == 500
        assert "tenant not configured" in response.json()["detail"]


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_returns_connector_status(self, client: TestClient) -> None:
        response = client.get("/api/connectors/teams/status")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "teams"
        assert data["status"] == "healthy"
        assert data["documents_synced"] == 5

    def test_returns_404_when_connector_not_registered(self, scheduler: MagicMock) -> None:
        empty_registry = ConnectorRegistry()
        app = _make_app(empty_registry, scheduler)
        c = TestClient(app, raise_server_exceptions=False)
        response = c.get("/api/connectors/teams/status")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /sync
# ---------------------------------------------------------------------------


class TestTriggerSync:
    def test_returns_sync_started(self, client: TestClient) -> None:
        response = client.post("/api/connectors/teams/sync")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sync_started"

    def test_returns_404_when_connector_not_registered(self, scheduler: MagicMock) -> None:
        empty_registry = ConnectorRegistry()
        app = _make_app(empty_registry, scheduler)
        c = TestClient(app, raise_server_exceptions=False)
        response = c.post("/api/connectors/teams/sync")
        assert response.status_code == 404

    def test_uses_default_503_when_no_scheduler_override(self) -> None:
        empty_registry = ConnectorRegistry()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_connector_registry] = lambda: empty_registry
        c = TestClient(app, raise_server_exceptions=False)
        response = c.post("/api/connectors/teams/sync")
        assert response.status_code == 503


# ---------------------------------------------------------------------------
# PUT /config
# ---------------------------------------------------------------------------


class TestUpdateConfig:
    def test_updates_config_and_reschedules(
        self,
        client: TestClient,
        connector: TeamsTranscriptConnector,
        scheduler: MagicMock,
    ) -> None:
        response = client.put(
            "/api/connectors/teams/config",
            json={"sync_interval_minutes": 15},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert data["sync_interval_minutes"] == 15

        assert connector._config.sync_interval_minutes == 15
        scheduler.reschedule_connector.assert_called_once_with("teams", 900)

    def test_returns_404_when_connector_not_registered(self, scheduler: MagicMock) -> None:
        empty_registry = ConnectorRegistry()
        app = _make_app(empty_registry, scheduler)
        c = TestClient(app, raise_server_exceptions=False)
        response = c.put(
            "/api/connectors/teams/config",
            json={"sync_interval_minutes": 15},
        )
        assert response.status_code == 404

    def test_rejects_zero_interval(self, client: TestClient) -> None:
        response = client.put(
            "/api/connectors/teams/config",
            json={"sync_interval_minutes": 0},
        )
        assert response.status_code == 422
