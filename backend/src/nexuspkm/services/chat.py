"""ChatService — session management and RAG query processing.

Manages chat sessions and messages in SQLite, and drives the RAG pipeline:
  1. Retrieve context from HybridRetriever
  2. Stream LLM response tokens
  3. Yield sources, follow-up suggestions, done frame

Spec: F-005 FR-1, FR-3, FR-4
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog

from nexuspkm.engine.retrieval import HybridRetriever
from nexuspkm.models.chat import ChatMessage, ChatSession
from nexuspkm.models.document import SourceAttribution
from nexuspkm.providers.base import BaseLLMProvider

logger = structlog.get_logger(__name__)

_SCHEMA_DDL = """\
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role         TEXT NOT NULL,
    content      TEXT NOT NULL,
    sources_json TEXT NOT NULL DEFAULT '[]',
    timestamp    TEXT NOT NULL
);
"""

_SYSTEM_PROMPT = (
    "You are NexusPKM, a personal knowledge assistant. "
    "Answer using the provided context. Cite sources with [1], [2] notation."
)

_CONTEXT_WINDOW = 10


class ChatService:
    """SQLite-backed chat session management with RAG query processing."""

    def __init__(
        self,
        retriever: HybridRetriever,
        llm: BaseLLMProvider,
        db_path: Path,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        self._db_path = db_path

    async def init(self) -> None:
        """Create tables and enable foreign keys."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._init_sync)

    def _init_sync(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(_SCHEMA_DDL)

    # ------------------------------------------------------------------
    # Session CRUD
    # ------------------------------------------------------------------

    async def create_session(self, first_message: str) -> ChatSession:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._create_session_sync, first_message)

    def _create_session_sync(self, first_message: str) -> ChatSession:
        session_id = str(uuid.uuid4())
        title = first_message[:50]
        now = datetime.now(tz=UTC)
        now_iso = now.isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?,?,?,?)",
                (session_id, title, now_iso, now_iso),
            )
        return ChatSession(
            id=session_id,
            title=title,
            messages=[],
            created_at=now,
            updated_at=now,
        )

    async def get_session(self, session_id: str) -> ChatSession | None:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_session_sync, session_id)

    def _get_session_sync(self, session_id: str) -> ChatSession | None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            row = conn.execute(
                "SELECT id, title, created_at, updated_at FROM sessions WHERE id=?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            sid, title, created_at, updated_at = row
            msg_rows = conn.execute(
                "SELECT id, role, content, sources_json, timestamp FROM messages "
                "WHERE session_id=? ORDER BY timestamp ASC",
                (session_id,),
            ).fetchall()

        messages = []
        for msg_id, role, content, sources_json, timestamp in msg_rows:
            sources_data = json.loads(sources_json)
            sources = [SourceAttribution.model_validate(s) for s in sources_data]
            messages.append(
                ChatMessage(
                    id=msg_id,
                    role=role,
                    content=content,
                    sources=sources,
                    timestamp=datetime.fromisoformat(timestamp),
                )
            )

        return ChatSession(
            id=sid,
            title=title,
            messages=messages,
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
        )

    async def list_sessions(self) -> list[ChatSession]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._list_sessions_sync)

    def _list_sessions_sync(self) -> list[ChatSession]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at FROM sessions ORDER BY created_at DESC"
            ).fetchall()
        return [
            ChatSession(
                id=sid,
                title=title,
                messages=[],
                created_at=datetime.fromisoformat(created_at),
                updated_at=datetime.fromisoformat(updated_at),
            )
            for sid, title, created_at, updated_at in rows
        ]

    async def delete_session(self, session_id: str) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._delete_session_sync, session_id)

    def _delete_session_sync(self, session_id: str) -> bool:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Query processing
    # ------------------------------------------------------------------

    async def process_query(self, session_id: str, query: str) -> AsyncIterator[dict[str, object]]:
        """Process a user query, yielding wire-protocol frames."""
        # Search mode: no LLM
        if query.startswith("/search ") or query.startswith("/graph "):
            prefix_len = 8 if query.startswith("/search ") else 7
            search_query = query[prefix_len:]
            async for frame in self._search_mode(search_query):
                yield frame
            return

        # RAG mode
        async for frame in self._rag_mode(session_id, query):
            yield frame

    async def _search_mode(self, query: str) -> AsyncIterator[dict[str, object]]:
        result = await self._retriever.retrieve(query, top_k=5)
        yield {
            "type": "sources",
            "sources": [s.model_dump(mode="json") for s in result.sources],
        }
        yield {"type": "done"}

    async def _rag_mode(self, session_id: str, query: str) -> AsyncIterator[dict[str, object]]:
        # 1. Load prior messages (last N)
        prior_messages = await self._load_prior_messages(session_id)

        # 2. Retrieve context
        result = await self._retriever.retrieve(query, top_k=5)

        # 3. Build numbered excerpts
        context_parts = []
        for i, source in enumerate(result.sources, 1):
            context_parts.append(f"[{i}] {source.title}\n{source.excerpt}")
        context_text = "\n\n".join(context_parts)

        # 4. Build messages list for LLM
        system_msg = {"role": "system", "content": f"{_SYSTEM_PROMPT}\n\nContext:\n{context_text}"}
        llm_messages: list[dict[str, str]] = [system_msg]
        llm_messages.extend(prior_messages)
        llm_messages.append({"role": "user", "content": query})

        # 5. Stream LLM response
        full_response = ""
        async for chunk in await self._llm.stream(llm_messages):
            full_response += chunk
            yield {"type": "chunk", "content": chunk}

        # 6. Yield sources
        sources_dicts = [s.model_dump(mode="json") for s in result.sources]
        yield {"type": "sources", "sources": sources_dicts}

        # 7. Generate follow-up suggestions
        suggestions = await self._generate_follow_ups(llm_messages, full_response)
        yield {"type": "suggestions", "suggestions": suggestions}

        # 8. Done
        yield {"type": "done"}

        # 9. Persist messages
        await self._persist_messages(session_id, query, full_response, sources_dicts)

    async def _load_prior_messages(self, session_id: str) -> list[dict[str, str]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._load_prior_messages_sync, session_id)

    def _load_prior_messages_sync(self, session_id: str) -> list[dict[str, str]]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages "
                "WHERE session_id=? ORDER BY timestamp DESC LIMIT ?",
                (session_id, _CONTEXT_WINDOW),
            ).fetchall()
        # Reverse to chronological order
        rows.reverse()
        return [{"role": role, "content": content} for role, content in rows]

    async def _generate_follow_ups(
        self,
        conversation: list[dict[str, str]],
        assistant_response: str,
    ) -> list[str]:
        follow_up_prompt = (
            "Suggest 3 short follow-up questions as a JSON array of strings. "
            "Reply with ONLY the JSON array."
        )
        messages = [
            *conversation,
            {"role": "assistant", "content": assistant_response},
            {"role": "user", "content": follow_up_prompt},
        ]
        try:
            response = await self._llm.generate(messages)
            result: list[str] = json.loads(response.content)
            return result
        except (json.JSONDecodeError, TypeError, KeyError):
            return []

    async def _persist_messages(
        self,
        session_id: str,
        query: str,
        response: str,
        sources_dicts: list[dict[str, object]],
    ) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self._persist_messages_sync, session_id, query, response, sources_dicts
        )

    def _persist_messages_sync(
        self,
        session_id: str,
        query: str,
        response: str,
        sources_dicts: list[dict[str, object]],
    ) -> None:
        now = datetime.now(tz=UTC)
        user_ts = now.isoformat()
        # +1ms to preserve ordering
        assistant_ts = (now + timedelta(milliseconds=1)).isoformat()
        user_id = str(uuid.uuid4())
        assistant_id = str(uuid.uuid4())

        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                "INSERT INTO messages (id, session_id, role, content, sources_json, timestamp) "
                "VALUES (?,?,?,?,?,?)",
                (user_id, session_id, "user", query, "[]", user_ts),
            )
            conn.execute(
                "INSERT INTO messages (id, session_id, role, content, sources_json, timestamp) "
                "VALUES (?,?,?,?,?,?)",
                (
                    assistant_id,
                    session_id,
                    "assistant",
                    response,
                    json.dumps(sources_dicts),
                    assistant_ts,
                ),
            )
            conn.execute(
                "UPDATE sessions SET updated_at=? WHERE id=?",
                (assistant_ts, session_id),
            )
