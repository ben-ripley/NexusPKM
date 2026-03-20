"""Unit tests for ChatService.

Tests: session CRUD, process_query RAG flow, /search mode, context window,
title truncation, follow-up JSON parsing.
Spec: F-005
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nexuspkm.models.chat import ChatSession
from nexuspkm.models.document import RetrievalResult, SourceAttribution, SourceType
from nexuspkm.services.chat import ChatService

_NOW = "2026-03-18T12:00:00+00:00"


def _make_source(title: str = "Doc 1", score: float = 0.8) -> SourceAttribution:
    return SourceAttribution(
        document_id="doc-1",
        title=title,
        source_type=SourceType.OBSIDIAN_NOTE,
        source_id="note-1",
        excerpt="Some relevant excerpt",
        relevance_score=score,
        created_at=_NOW,
    )


def _make_retrieval_result(
    sources: list[SourceAttribution] | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        chunks=[],
        entities=[],
        relationships=[],
        combined_score=0.8,
        sources=sources or [_make_source()],
    )


def _make_service(tmp_path: Path) -> tuple[ChatService, MagicMock, MagicMock]:
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=_make_retrieval_result())

    llm = MagicMock()

    async def _fake_stream(messages: list[dict[str, str]], **kwargs: object) -> AsyncIterator[str]:
        async def _gen() -> AsyncIterator[str]:
            for token in ["Hello", " world"]:
                yield token

        return _gen()

    llm.stream = AsyncMock(side_effect=_fake_stream)
    llm.generate = AsyncMock(
        return_value=MagicMock(content='["What else?", "Tell me more", "Any details?"]')
    )

    svc = ChatService(retriever, llm, tmp_path / "chat.db")
    return svc, retriever, llm


@pytest.fixture
async def svc(tmp_path: Path) -> ChatService:
    service, _, _ = _make_service(tmp_path)
    await service.init()
    return service


@pytest.fixture
async def svc_with_mocks(
    tmp_path: Path,
) -> tuple[ChatService, MagicMock, MagicMock]:
    service, retriever, llm = _make_service(tmp_path)
    await service.init()
    return service, retriever, llm


# -------------------------------------------------------------------
# Session CRUD
# -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_session(svc: ChatService) -> None:
    session = await svc.create_session("Hello world")
    assert isinstance(session, ChatSession)
    assert session.title == "Hello world"
    assert session.messages == []
    assert session.id


@pytest.mark.asyncio
async def test_create_session_truncates_title_at_50_chars(svc: ChatService) -> None:
    long_msg = "A" * 100
    session = await svc.create_session(long_msg)
    assert len(session.title) == 50
    assert session.title == "A" * 50


@pytest.mark.asyncio
async def test_get_session_returns_none_for_missing(svc: ChatService) -> None:
    result = await svc.get_session("nonexistent-id")
    assert result is None


@pytest.mark.asyncio
async def test_list_sessions_returns_newest_first(tmp_path: Path) -> None:
    # Use explicit timestamps far enough apart to avoid sub-millisecond collisions.
    service, _, _ = _make_service(tmp_path)
    await service.init()
    s1 = await service.create_session("First session")
    # Insert s2 with a timestamp 1 second later via direct DB write so ordering is deterministic.
    s2_id = str(uuid.uuid4())
    s2_ts = (
        datetime.fromisoformat(s1.created_at.isoformat())
        .replace(second=s1.created_at.second + 1)
        .isoformat()
    )
    conn = sqlite3.connect(str(tmp_path / "chat.db"))
    conn.execute(
        "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?,?,?,?)",
        (s2_id, "Second session", s2_ts, s2_ts),
    )
    conn.commit()
    conn.close()

    sessions = await service.list_sessions()
    assert len(sessions) == 2
    assert sessions[0].id == s2_id
    assert sessions[1].id == s1.id
    # Metadata only: no messages
    assert sessions[0].messages == []
    assert sessions[1].messages == []


@pytest.mark.asyncio
async def test_delete_session_returns_true(svc: ChatService) -> None:
    session = await svc.create_session("To delete")
    result = await svc.delete_session(session.id)
    assert result is True
    assert await svc.get_session(session.id) is None


@pytest.mark.asyncio
async def test_delete_session_returns_false_for_missing(svc: ChatService) -> None:
    result = await svc.delete_session("nonexistent-id")
    assert result is False


# -------------------------------------------------------------------
# process_query — RAG mode
# -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_query_rag_yields_chunks_sources_suggestions_done(
    svc_with_mocks: tuple[ChatService, MagicMock, MagicMock],
) -> None:
    svc, _, _ = svc_with_mocks
    session = await svc.create_session("test")
    frames: list[dict[str, object]] = []
    async for frame in svc.process_query(session.id, "What happened?"):
        frames.append(frame)

    types = [f["type"] for f in frames]
    # Must have chunks, then sources, then suggestions, then done
    assert "chunk" in types
    assert "sources" in types
    assert "suggestions" in types
    assert types[-1] == "done"
    # Order: all chunks before sources, sources before suggestions, suggestions before done
    chunk_idx = max(i for i, t in enumerate(types) if t == "chunk")
    sources_idx = types.index("sources")
    suggestions_idx = types.index("suggestions")
    done_idx = types.index("done")
    assert chunk_idx < sources_idx < suggestions_idx < done_idx


@pytest.mark.asyncio
async def test_process_query_rag_llm_called_once(
    svc_with_mocks: tuple[ChatService, MagicMock, MagicMock],
) -> None:
    svc, _, llm = svc_with_mocks
    session = await svc.create_session("test")
    async for _ in svc.process_query(session.id, "query"):
        pass
    # stream called exactly once for the RAG response
    assert llm.stream.call_count == 1


# -------------------------------------------------------------------
# process_query — /search mode
# -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_query_search_mode_no_llm(
    svc_with_mocks: tuple[ChatService, MagicMock, MagicMock],
) -> None:
    svc, retriever, llm = svc_with_mocks
    session = await svc.create_session("test")
    frames: list[dict[str, object]] = []
    async for frame in svc.process_query(session.id, "/search what"):
        frames.append(frame)

    types = [f["type"] for f in frames]
    assert "sources" in types
    assert "done" in types
    # LLM should NOT be called
    llm.stream.assert_not_called()
    llm.generate.assert_not_called()


# -------------------------------------------------------------------
# process_query — context window
# -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_query_context_window_last_10_messages(
    tmp_path: Path,
) -> None:
    svc, _, llm = _make_service(tmp_path)
    await svc.init()
    session = await svc.create_session("test")

    # Insert 15 messages (alternating user/assistant)
    for i in range(15):
        role = "user" if i % 2 == 0 else "assistant"
        content = f"Message {i}"
        conn = sqlite3.connect(str(tmp_path / "chat.db"))
        conn.execute("PRAGMA foreign_keys = ON")
        msg_id = str(uuid.uuid4())
        ts = datetime(2026, 3, 18, 12, 0, i, tzinfo=UTC).isoformat()
        conn.execute(
            "INSERT INTO messages (id, session_id, role, content, sources_json, timestamp) "
            "VALUES (?,?,?,?,?,?)",
            (msg_id, session.id, role, content, "[]", ts),
        )
        conn.commit()
        conn.close()

    # Now process a query and check LLM was called with at most 10 prior messages
    async for _ in svc.process_query(session.id, "new question"):
        pass

    # The stream call should have been made with messages list
    call_args = llm.stream.call_args
    messages_sent = call_args[0][0]  # first positional arg
    # Filter out system prompt and user query — prior messages are in between
    # System prompt is messages_sent[0], context messages follow, then user query is last
    prior = [
        m
        for m in messages_sent
        if m["role"] in ("user", "assistant") and m["content"] != "new question"
    ]
    assert len(prior) <= 10


# -------------------------------------------------------------------
# process_query — malformed follow-up JSON
# -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_query_follow_up_parses_malformed_json(
    tmp_path: Path,
) -> None:
    svc, _, llm = _make_service(tmp_path)
    await svc.init()
    # Make follow-up generation return non-JSON
    llm.generate = AsyncMock(return_value=MagicMock(content="not valid json"))
    session = await svc.create_session("test")
    frames: list[dict[str, object]] = []
    async for frame in svc.process_query(session.id, "query"):
        frames.append(frame)

    suggestions_frame = next(f for f in frames if f["type"] == "suggestions")
    assert suggestions_frame["suggestions"] == []
