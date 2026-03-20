"""Chat API — REST session management + WebSocket streaming chat.

Endpoints:
  GET    /api/chat/sessions           list sessions
  GET    /api/chat/sessions/{id}      get session with messages
  POST   /api/chat/sessions           create session
  DELETE /api/chat/sessions/{id}      delete session (204)
  WS     /ws/chat/{session_id}        streaming chat

Spec: F-005 FR-1, FR-2
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from nexuspkm.models.chat import ChatSession
from nexuspkm.services.chat import ChatService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["chat"])


# ---------------------------------------------------------------------------
# Dependency sentinel (overridden in main.py lifespan)
# ---------------------------------------------------------------------------


def get_chat_service() -> ChatService:
    """Dependency: returns the active ChatService."""
    raise HTTPException(status_code=503, detail="Chat service not initialised")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    first_message: str


class SessionMetaResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@router.get("/api/chat/sessions", response_model=list[SessionMetaResponse])
async def list_sessions(
    svc: Annotated[ChatService, Depends(get_chat_service)],
) -> list[SessionMetaResponse]:
    sessions = await svc.list_sessions()
    return [
        SessionMetaResponse(
            id=s.id,
            title=s.title,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
        )
        for s in sessions
    ]


@router.get("/api/chat/sessions/{session_id}", response_model=ChatSession)
async def get_session(
    session_id: str,
    svc: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatSession:
    session = await svc.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/api/chat/sessions", response_model=ChatSession)
async def create_session(
    payload: CreateSessionRequest,
    svc: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatSession:
    return await svc.create_session(payload.first_message)


@router.delete("/api/chat/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    svc: Annotated[ChatService, Depends(get_chat_service)],
) -> Response:
    deleted = await svc.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws/chat/{session_id}")
async def websocket_chat(
    session_id: str,
    websocket: WebSocket,
    svc: Annotated[ChatService, Depends(get_chat_service)],
) -> None:
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") != "query":
                await websocket.send_json({"type": "error", "message": "expected type=query"})
                continue
            query = data.get("content", "")
            try:
                async for frame in svc.process_query(session_id, query):
                    await websocket.send_json(frame)
            except Exception as exc:
                logger.warning("websocket.query_error", error=str(exc))
                await websocket.send_json({"type": "error", "message": str(exc)})
    except WebSocketDisconnect:
        pass
