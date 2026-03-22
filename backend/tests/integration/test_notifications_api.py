"""Integration tests for notifications REST + WebSocket API.

Spec: F-013
NXP-87
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from nexuspkm.api.notifications import get_proactive_service
from nexuspkm.main import app
from nexuspkm.models.notification import (
    Notification,
    NotificationPreferences,
    NotificationPriority,
    NotificationType,
)
from nexuspkm.services.proactive import ProactiveService


def _make_notification(nid: str = "n-1", read: bool = False) -> Notification:
    return Notification(
        id=nid,
        type=NotificationType.INSIGHT,
        title="Test notification",
        summary="A summary",
        priority=NotificationPriority.MEDIUM,
        data={},
        read=read,
        created_at=datetime.now(tz=UTC),
    )


def _make_mock_service() -> MagicMock:
    svc = MagicMock(spec=ProactiveService)

    svc.list_notifications = AsyncMock(return_value=[_make_notification("n-1")])
    svc.get_unread_count = AsyncMock(return_value=1)
    svc.mark_read = AsyncMock(return_value=True)
    svc.dismiss = AsyncMock(return_value=True)
    svc.get_preferences = AsyncMock(return_value=NotificationPreferences())
    svc.save_preferences = AsyncMock(return_value=None)
    svc.get_meeting_context = AsyncMock(return_value=None)

    # WS manager — connect must call ws.accept() so the socket is in CONNECTED state
    from fastapi import WebSocket as _WS

    async def _ws_connect(ws: _WS) -> None:
        await ws.accept()

    svc.ws_manager = MagicMock()
    svc.ws_manager.connect = _ws_connect
    svc.ws_manager.disconnect = MagicMock()

    return svc


@pytest.fixture
def mock_service() -> MagicMock:
    return _make_mock_service()


@pytest.fixture
def client(mock_service: MagicMock) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_proactive_service] = lambda: mock_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_proactive_service, None)


# ---------------------------------------------------------------------------
# GET /api/notifications
# ---------------------------------------------------------------------------


def test_list_notifications_returns_200(client: TestClient) -> None:
    response = client.get("/api/notifications")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == "n-1"


def test_list_notifications_unread_only_param(client: TestClient, mock_service: MagicMock) -> None:
    mock_service.list_notifications = AsyncMock(return_value=[])
    response = client.get("/api/notifications?unread_only=true")
    assert response.status_code == 200
    mock_service.list_notifications.assert_called_once()
    call_kwargs = mock_service.list_notifications.call_args
    assert call_kwargs.kwargs.get("unread_only") is True


def test_list_notifications_limit_param(client: TestClient, mock_service: MagicMock) -> None:
    mock_service.list_notifications = AsyncMock(return_value=[])
    response = client.get("/api/notifications?limit=5&offset=10")
    assert response.status_code == 200
    call_kwargs = mock_service.list_notifications.call_args
    assert call_kwargs.kwargs.get("limit") == 5
    assert call_kwargs.kwargs.get("offset") == 10


# ---------------------------------------------------------------------------
# GET /api/notifications/unread-count
# ---------------------------------------------------------------------------


def test_get_unread_count_returns_200(client: TestClient) -> None:
    response = client.get("/api/notifications/unread-count")
    assert response.status_code == 200
    assert response.json() == {"count": 1}


# ---------------------------------------------------------------------------
# PUT /api/notifications/{id}/read
# ---------------------------------------------------------------------------


def test_mark_read_returns_204(client: TestClient) -> None:
    response = client.put("/api/notifications/n-1/read")
    assert response.status_code == 204


def test_mark_read_not_found_returns_404(client: TestClient, mock_service: MagicMock) -> None:
    mock_service.mark_read = AsyncMock(return_value=False)
    response = client.put("/api/notifications/missing/read")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/notifications/{id}
# ---------------------------------------------------------------------------


def test_dismiss_returns_204(client: TestClient) -> None:
    response = client.delete("/api/notifications/n-1")
    assert response.status_code == 204


def test_dismiss_not_found_returns_404(client: TestClient, mock_service: MagicMock) -> None:
    mock_service.dismiss = AsyncMock(return_value=False)
    response = client.delete("/api/notifications/missing")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/context/preferences
# ---------------------------------------------------------------------------


def test_get_preferences_returns_200(client: TestClient) -> None:
    response = client.get("/api/context/preferences")
    assert response.status_code == 200
    data = response.json()
    assert "meeting_prep_enabled" in data
    assert "related_content_enabled" in data
    assert data["meeting_prep_enabled"] is True


# ---------------------------------------------------------------------------
# PUT /api/context/preferences
# ---------------------------------------------------------------------------


def test_update_preferences_returns_200(client: TestClient, mock_service: MagicMock) -> None:
    payload = {
        "meeting_prep_enabled": False,
        "meeting_prep_lead_time_minutes": 45,
        "related_content_enabled": True,
        "related_content_threshold": 0.6,
        "contradiction_alerts_enabled": False,
        "webhook_url": None,
    }
    # Make get_preferences return the saved values after save
    mock_service.get_preferences = AsyncMock(
        return_value=NotificationPreferences(
            meeting_prep_enabled=False,
            meeting_prep_lead_time_minutes=45,
            related_content_threshold=0.6,
            contradiction_alerts_enabled=False,
        )
    )
    response = client.put("/api/context/preferences", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["meeting_prep_enabled"] is False
    mock_service.save_preferences.assert_called_once()


# ---------------------------------------------------------------------------
# GET /api/context/meeting/{meeting_id}
# ---------------------------------------------------------------------------


def test_get_meeting_context_none_returns_404(client: TestClient, mock_service: MagicMock) -> None:
    mock_service.get_meeting_context = AsyncMock(return_value=None)
    response = client.get("/api/context/meeting/m-1")
    assert response.status_code == 404


def test_get_meeting_context_returns_200(client: TestClient, mock_service: MagicMock) -> None:
    from nexuspkm.models.notification import MeetingContext

    ctx = MeetingContext(
        meeting_id="m-1",
        meeting_title="Sprint Review",
        meeting_time=None,
        attendees=[],
        previous_meetings=[],
        related_tickets=[],
        related_notes=[],
        related_emails=[],
        open_action_items=[],
        suggested_agenda=[],
    )
    mock_service.get_meeting_context = AsyncMock(return_value=ctx)
    response = client.get("/api/context/meeting/m-1")
    assert response.status_code == 200
    data = response.json()
    assert data["meeting_id"] == "m-1"
    assert data["meeting_title"] == "Sprint Review"


# ---------------------------------------------------------------------------
# WebSocket /ws/notifications
# ---------------------------------------------------------------------------


def test_websocket_notifications_connects(client: TestClient) -> None:
    # Verify the WebSocket endpoint accepts a connection without error
    with client.websocket_connect("/ws/notifications"):
        pass  # connection accepted and cleanly disconnected
