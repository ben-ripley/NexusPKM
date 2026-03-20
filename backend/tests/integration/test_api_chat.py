"""Integration tests for chat API endpoints and WebSocket.

Tests the /api/chat/* REST routes and /ws/chat/{session_id} WebSocket.
Spec: F-005
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from nexuspkm.api.chat import get_chat_service
from nexuspkm.main import app
from nexuspkm.models.document import RetrievalResult, SourceAttribution, SourceType
from nexuspkm.services.chat import ChatService

_NOW = "2026-03-18T12:00:00+00:00"


def _make_source() -> SourceAttribution:
    return SourceAttribution(
        document_id="doc-1",
        title="Test Doc",
        source_type=SourceType.OBSIDIAN_NOTE,
        source_id="note-1",
        excerpt="Relevant excerpt",
        relevance_score=0.8,
        created_at=_NOW,
    )


def _make_retrieval_result() -> RetrievalResult:
    return RetrievalResult(
        chunks=[],
        entities=[],
        relationships=[],
        combined_score=0.8,
        sources=[_make_source()],
    )


def _make_chat_service(tmp_path_factory: pytest.TempPathFactory) -> ChatService:
    tmp = tmp_path_factory.mktemp("chat")
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=_make_retrieval_result())

    llm = MagicMock()

    async def _fake_stream(messages: list[dict[str, str]], **kwargs: object) -> AsyncIterator[str]:
        async def _gen() -> AsyncIterator[str]:
            for token in ["Hello", " world"]:
                yield token

        return _gen()

    llm.stream = AsyncMock(side_effect=_fake_stream)
    llm.generate = AsyncMock(return_value=MagicMock(content='["Follow up?"]'))

    return ChatService(retriever, llm, tmp / "chat.db")


@pytest.fixture
def chat_client(tmp_path_factory: pytest.TempPathFactory) -> Generator[TestClient, None, None]:
    svc = _make_chat_service(tmp_path_factory)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(svc.init())
    finally:
        loop.close()
    app.dependency_overrides[get_chat_service] = lambda: svc
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_chat_service, None)


# -------------------------------------------------------------------
# REST endpoint tests
# -------------------------------------------------------------------


def test_list_sessions_empty(chat_client: TestClient) -> None:
    resp = chat_client.get("/api/chat/sessions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_session(chat_client: TestClient) -> None:
    resp = chat_client.post("/api/chat/sessions", json={"first_message": "hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "hello"
    assert "id" in data
    assert "created_at" in data


def test_get_session_not_found(chat_client: TestClient) -> None:
    resp = chat_client.get("/api/chat/sessions/bad-id")
    assert resp.status_code == 404


def test_get_session_found(chat_client: TestClient) -> None:
    create_resp = chat_client.post("/api/chat/sessions", json={"first_message": "test session"})
    session_id = create_resp.json()["id"]
    resp = chat_client.get(f"/api/chat/sessions/{session_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == session_id
    assert "messages" in data


def test_delete_session(chat_client: TestClient) -> None:
    create_resp = chat_client.post("/api/chat/sessions", json={"first_message": "to delete"})
    session_id = create_resp.json()["id"]
    resp = chat_client.delete(f"/api/chat/sessions/{session_id}")
    assert resp.status_code == 204


def test_delete_session_not_found(chat_client: TestClient) -> None:
    resp = chat_client.delete("/api/chat/sessions/bad-id")
    assert resp.status_code == 404


# -------------------------------------------------------------------
# WebSocket tests
# -------------------------------------------------------------------


def test_websocket_chat_full_flow(chat_client: TestClient) -> None:
    create_resp = chat_client.post("/api/chat/sessions", json={"first_message": "ws test"})
    session_id = create_resp.json()["id"]

    with chat_client.websocket_connect(f"/ws/chat/{session_id}") as ws:
        ws.send_json({"type": "query", "content": "hello"})
        frames = []
        while True:
            frame = ws.receive_json()
            frames.append(frame)
            if frame.get("type") == "done":
                break

    types = [f["type"] for f in frames]
    assert "chunk" in types
    assert "sources" in types
    assert "done" in types


def test_websocket_session_history_persisted(chat_client: TestClient) -> None:
    create_resp = chat_client.post("/api/chat/sessions", json={"first_message": "persist test"})
    session_id = create_resp.json()["id"]

    # Send a message via WS
    with chat_client.websocket_connect(f"/ws/chat/{session_id}") as ws:
        ws.send_json({"type": "query", "content": "first message"})
        while True:
            frame = ws.receive_json()
            if frame.get("type") == "done":
                break

    # Check messages persisted via REST
    resp = chat_client.get(f"/api/chat/sessions/{session_id}")
    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert len(messages) >= 2  # user + assistant
    roles = [m["role"] for m in messages]
    assert "user" in roles
    assert "assistant" in roles


def test_websocket_malformed_message_returns_error(chat_client: TestClient) -> None:
    create_resp = chat_client.post("/api/chat/sessions", json={"first_message": "error test"})
    session_id = create_resp.json()["id"]

    with chat_client.websocket_connect(f"/ws/chat/{session_id}") as ws:
        ws.send_json({"type": "invalid"})
        frame = ws.receive_json()
        assert frame["type"] == "error"
        assert "expected type=query" in frame["message"]
