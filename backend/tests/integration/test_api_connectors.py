"""Integration tests for the generic Connector management API endpoints.

Covers: api/connectors.generic_router
Spec ref: F-003 API endpoints
NXP-50 / NXP-59
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexuspkm.api.connectors import (
    generic_router,
    get_connector_registry,
    get_sync_scheduler,
)
from nexuspkm.connectors.base import BaseConnector, ConnectorStatus
from nexuspkm.connectors.ms_graph.teams import TeamsTranscriptConnector
from nexuspkm.connectors.registry import ConnectorRegistry
from nexuspkm.connectors.scheduler import SyncScheduler

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_app(registry: ConnectorRegistry, scheduler: SyncScheduler) -> FastAPI:
    app = FastAPI()
    app.include_router(generic_router)
    app.dependency_overrides[get_connector_registry] = lambda: registry
    app.dependency_overrides[get_sync_scheduler] = lambda: scheduler
    return app


@pytest.fixture
def mock_generic_connector() -> MagicMock:
    """A connector that does NOT implement the MS auth protocol."""
    connector = MagicMock(spec=BaseConnector)
    connector.name = "test_source"
    return connector


@pytest.fixture
def mock_ms_connector() -> MagicMock:
    """A connector that implements initiate_auth_flow / complete_auth_flow."""
    connector = MagicMock(spec=TeamsTranscriptConnector)
    connector.name = "test_ms"
    connector.initiate_auth_flow = AsyncMock(
        return_value=(
            MagicMock(
                user_code="ABCD-1234",
                verification_uri="https://microsoft.com/devicelogin",
                expires_in=900,
                message="Use code ABCD-1234 at https://microsoft.com/devicelogin",
            ),
            MagicMock(),  # AuthFlowContext
        )
    )
    connector.complete_auth_flow = AsyncMock(return_value=True)
    return connector


@pytest.fixture
def registry(
    mock_generic_connector: MagicMock,
    mock_ms_connector: MagicMock,
) -> ConnectorRegistry:
    reg = ConnectorRegistry()
    reg._connectors["test_source"] = mock_generic_connector
    reg._statuses["test_source"] = ConnectorStatus(
        name="test_source",
        status="healthy",
        documents_synced=10,
        last_error=None,
    )
    reg._connectors["test_ms"] = mock_ms_connector
    reg._statuses["test_ms"] = ConnectorStatus(
        name="test_ms",
        status="degraded",
        documents_synced=3,
        last_error="token expired",
    )
    return reg


@pytest.fixture
def mock_scheduler() -> MagicMock:
    sched = MagicMock(spec=SyncScheduler)
    sched.trigger_sync = AsyncMock()
    return sched


@pytest.fixture
def connector_client(registry: ConnectorRegistry, mock_scheduler: MagicMock) -> TestClient:
    app = _make_app(registry, mock_scheduler)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /api/connectors/status
# ---------------------------------------------------------------------------


class TestGetAllStatuses:
    def test_returns_all_connectors(self, connector_client: TestClient) -> None:
        response = connector_client.get("/api/connectors/status")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = {item["name"] for item in data}
        assert names == {"test_source", "test_ms"}

    def test_returns_correct_status_fields(self, connector_client: TestClient) -> None:
        response = connector_client.get("/api/connectors/status")

        assert response.status_code == 200
        by_name = {item["name"]: item for item in response.json()}

        src = by_name["test_source"]
        assert src["status"] == "healthy"
        assert src["documents_synced"] == 10
        assert src["last_error"] is None

        ms = by_name["test_ms"]
        assert ms["status"] == "degraded"
        assert ms["documents_synced"] == 3
        assert ms["last_error"] == "token expired"

    def test_empty_registry_returns_empty_list(self, mock_scheduler: MagicMock) -> None:
        empty_registry = ConnectorRegistry()
        app = _make_app(empty_registry, mock_scheduler)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/api/connectors/status")

        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# POST /api/connectors/{name}/sync
# ---------------------------------------------------------------------------


class TestTriggerSync:
    def test_known_connector_returns_sync_started(
        self,
        connector_client: TestClient,
        mock_scheduler: MagicMock,
    ) -> None:
        response = connector_client.post("/api/connectors/test_source/sync")

        assert response.status_code == 200
        assert response.json()["status"] == "sync_started"

    def test_unknown_connector_returns_404(self, connector_client: TestClient) -> None:
        response = connector_client.post("/api/connectors/no_such_connector/sync")

        assert response.status_code == 404

    def test_calls_scheduler_trigger_sync_with_name(
        self,
        connector_client: TestClient,
        mock_scheduler: MagicMock,
    ) -> None:
        connector_client.post("/api/connectors/test_source/sync")

        mock_scheduler.trigger_sync.assert_called_once_with("test_source")


# ---------------------------------------------------------------------------
# PUT /api/connectors/{name}/config
# ---------------------------------------------------------------------------


class TestUpdateConfig:
    def test_known_connector_returns_updated(self, connector_client: TestClient) -> None:
        response = connector_client.put(
            "/api/connectors/test_source/config",
            json={"sync_interval_minutes": 60},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert data["sync_interval_minutes"] == 60

    def test_unknown_connector_returns_404(self, connector_client: TestClient) -> None:
        response = connector_client.put(
            "/api/connectors/no_such_connector/config",
            json={"sync_interval_minutes": 60},
        )

        assert response.status_code == 404

    def test_interval_zero_returns_422(self, connector_client: TestClient) -> None:
        response = connector_client.put(
            "/api/connectors/test_source/config",
            json={"sync_interval_minutes": 0},
        )

        assert response.status_code == 422

    def test_interval_max_1440_accepted(self, connector_client: TestClient) -> None:
        response = connector_client.put(
            "/api/connectors/test_source/config",
            json={"sync_interval_minutes": 1440},
        )

        assert response.status_code == 200
        assert response.json()["sync_interval_minutes"] == 1440

    def test_calls_reschedule_connector_with_seconds(
        self,
        connector_client: TestClient,
        mock_scheduler: MagicMock,
    ) -> None:
        connector_client.put(
            "/api/connectors/test_source/config",
            json={"sync_interval_minutes": 45},
        )

        mock_scheduler.reschedule_connector.assert_called_once_with("test_source", 45 * 60)


# ---------------------------------------------------------------------------
# POST /api/connectors/{name}/authenticate
# ---------------------------------------------------------------------------


class TestAuthenticate:
    def test_ms_connector_returns_device_code_info(
        self,
        connector_client: TestClient,
        mock_ms_connector: MagicMock,
    ) -> None:
        response = connector_client.post("/api/connectors/test_ms/authenticate")

        assert response.status_code == 200
        data = response.json()
        assert data["user_code"] == "ABCD-1234"
        assert data["verification_uri"] == "https://microsoft.com/devicelogin"
        assert data["expires_in"] == 900
        assert "message" in data

    def test_non_ms_connector_returns_400(self, connector_client: TestClient) -> None:
        response = connector_client.post("/api/connectors/test_source/authenticate")

        assert response.status_code == 400

    def test_unknown_connector_returns_404(self, connector_client: TestClient) -> None:
        response = connector_client.post("/api/connectors/no_such_connector/authenticate")

        assert response.status_code == 404

    def test_initiate_failure_returns_500(
        self,
        registry: ConnectorRegistry,
        mock_scheduler: MagicMock,
        mock_ms_connector: MagicMock,
    ) -> None:
        mock_ms_connector.initiate_auth_flow = AsyncMock(
            side_effect=RuntimeError("tenant not configured")
        )
        app = _make_app(registry, mock_scheduler)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/api/connectors/test_ms/authenticate")

        assert response.status_code == 500
        # Internal error detail must not be leaked to the caller
        assert "tenant not configured" not in response.json()["detail"]

    def test_background_task_polls_for_token(
        self,
        connector_client: TestClient,
        mock_ms_connector: MagicMock,
    ) -> None:
        connector_client.post("/api/connectors/test_ms/authenticate")

        # TestClient runs background tasks synchronously
        mock_ms_connector.complete_auth_flow.assert_called_once()
