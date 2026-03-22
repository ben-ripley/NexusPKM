"""Notifications & Context API — REST endpoints + WebSocket push.

Endpoints:
  GET    /api/notifications               list notifications
  GET    /api/notifications/unread-count  unread count
  PUT    /api/notifications/{id}/read     mark as read
  DELETE /api/notifications/{id}          dismiss
  GET    /api/context/meeting/{id}        meeting prep context
  GET    /api/context/preferences         notification preferences
  PUT    /api/context/preferences         update preferences
  WS     /ws/notifications                real-time push

Spec: F-013
NXP-87
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
)

from nexuspkm.models.notification import (
    MeetingContext,
    Notification,
    NotificationPreferences,
)
from nexuspkm.services.proactive import ProactiveService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["notifications"])


# ---------------------------------------------------------------------------
# Dependency sentinel (overridden in main.py lifespan)
# ---------------------------------------------------------------------------


def get_proactive_service() -> ProactiveService:
    """Dependency: returns the active ProactiveService."""
    raise HTTPException(  # pragma: no cover
        status_code=503, detail="Proactive service not initialised"
    )


# ---------------------------------------------------------------------------
# GET /api/notifications
# ---------------------------------------------------------------------------


@router.get("/api/notifications", response_model=list[Notification])
async def list_notifications(
    service: Annotated[ProactiveService, Depends(get_proactive_service)],
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Notification]:
    return await service.list_notifications(unread_only=unread_only, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# GET /api/notifications/unread-count
# ---------------------------------------------------------------------------


@router.get("/api/notifications/unread-count")
async def get_unread_count(
    service: Annotated[ProactiveService, Depends(get_proactive_service)],
) -> dict[str, int]:
    count = await service.get_unread_count()
    return {"count": count}


# ---------------------------------------------------------------------------
# PUT /api/notifications/{id}/read
# ---------------------------------------------------------------------------


@router.put("/api/notifications/{notification_id}/read", status_code=204)
async def mark_read(
    notification_id: str,
    service: Annotated[ProactiveService, Depends(get_proactive_service)],
) -> Response:
    found = await service.mark_read(notification_id)
    if not found:
        raise HTTPException(status_code=404, detail="Notification not found")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# DELETE /api/notifications/{id}
# ---------------------------------------------------------------------------


@router.delete("/api/notifications/{notification_id}", status_code=204)
async def dismiss_notification(
    notification_id: str,
    service: Annotated[ProactiveService, Depends(get_proactive_service)],
) -> Response:
    found = await service.dismiss(notification_id)
    if not found:
        raise HTTPException(status_code=404, detail="Notification not found")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# GET /api/context/meeting/{meeting_id}
# ---------------------------------------------------------------------------


@router.get("/api/context/meeting/{meeting_id}", response_model=MeetingContext)
async def get_meeting_context(
    meeting_id: str,
    service: Annotated[ProactiveService, Depends(get_proactive_service)],
) -> MeetingContext:
    ctx = await service.get_meeting_context(meeting_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return ctx


# ---------------------------------------------------------------------------
# GET /api/context/preferences
# ---------------------------------------------------------------------------


@router.get("/api/context/preferences", response_model=NotificationPreferences)
async def get_preferences(
    service: Annotated[ProactiveService, Depends(get_proactive_service)],
) -> NotificationPreferences:
    return await service.get_preferences()


# ---------------------------------------------------------------------------
# PUT /api/context/preferences
# ---------------------------------------------------------------------------


@router.put("/api/context/preferences", response_model=NotificationPreferences)
async def update_preferences(
    prefs: NotificationPreferences,
    service: Annotated[ProactiveService, Depends(get_proactive_service)],
) -> NotificationPreferences:
    await service.save_preferences(prefs)
    return await service.get_preferences()


# ---------------------------------------------------------------------------
# WS /ws/notifications
# ---------------------------------------------------------------------------


@router.websocket("/ws/notifications")
async def notification_ws(
    ws: WebSocket,
    service: Annotated[ProactiveService, Depends(get_proactive_service)],
) -> None:
    await service.ws_manager.connect(ws)
    logger.info("notification_ws.connected")
    try:
        while True:
            # Keep alive — client may send pings; we just drain the socket
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        service.ws_manager.disconnect(ws)
        logger.info("notification_ws.disconnected")
