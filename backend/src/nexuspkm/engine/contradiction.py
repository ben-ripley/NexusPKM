"""ContradictionDetector — detect conflicts between new and existing entity properties.

Detects date, status, and assignment conflicts. Persists contradictions to
SQLite and provides list/resolve operations.

Spec: F-006 FR-5
"""

from __future__ import annotations

import asyncio
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from nexuspkm.models.contradiction import Contradiction, ContradictionType

logger = structlog.get_logger(__name__)

_SCHEMA_DDL = """\
CREATE TABLE IF NOT EXISTS contradictions (
    id              TEXT PRIMARY KEY,
    entity_id       TEXT NOT NULL,
    field_name      TEXT NOT NULL,
    old_value       TEXT NOT NULL,
    new_value       TEXT NOT NULL,
    source_doc_id   TEXT NOT NULL,
    detected_at     TEXT NOT NULL,
    resolved        INTEGER NOT NULL DEFAULT 0,
    resolved_at     TEXT,
    contradiction_type TEXT NOT NULL DEFAULT 'status_conflict'
);
"""

# Fields that trigger each contradiction type when they change
_DATE_FIELDS = frozenset({"due_date", "made_at", "date", "deadline"})
_STATUS_FIELDS = frozenset({"status"})
_ASSIGNMENT_FIELDS = frozenset({"assignee_id", "assignee", "owner_id", "owner"})


class ContradictionDetector:
    """Detect and persist contradictions between incoming and existing entity data."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> Path:
        return self._db_path

    async def init(self) -> None:
        """Create tables if they do not exist (call once at startup)."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._ensure_schema)

    def _ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.executescript(_SCHEMA_DDL)

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    async def detect(
        self,
        entity_id: str,
        existing_properties: dict[str, Any],
        new_properties: dict[str, Any],
        source_doc_id: str,
    ) -> list[Contradiction]:
        """Compare new_properties against existing_properties and return contradictions."""
        contradictions: list[Contradiction] = []
        now = datetime.now(tz=UTC)

        for field, new_value in new_properties.items():
            if field not in existing_properties:
                continue
            old_value = existing_properties[field]
            if old_value == new_value:
                continue

            contradiction_type = self._classify_field(field)
            if contradiction_type is None:
                continue

            contradictions.append(
                Contradiction(
                    id=str(uuid.uuid4()),
                    entity_id=entity_id,
                    field_name=field,
                    old_value=str(old_value),
                    new_value=str(new_value),
                    source_doc_id=source_doc_id,
                    detected_at=now,
                    contradiction_type=contradiction_type,
                )
            )

        return contradictions

    @staticmethod
    def _classify_field(field: str) -> ContradictionType | None:
        if field in _DATE_FIELDS:
            return ContradictionType.DATE_CONFLICT
        if field in _STATUS_FIELDS:
            return ContradictionType.STATUS_CONFLICT
        if field in _ASSIGNMENT_FIELDS:
            return ContradictionType.ASSIGNMENT_CONFLICT
        return None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def persist(self, contradictions: list[Contradiction]) -> None:
        """Write contradictions to SQLite."""
        if not contradictions:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._persist_sync, contradictions)

    def _persist_sync(self, contradictions: list[Contradiction]) -> None:
        with sqlite3.connect(self._db_path) as conn:
            for c in contradictions:
                conn.execute(
                    "INSERT OR IGNORE INTO contradictions "
                    "(id, entity_id, field_name, old_value, new_value, "
                    "source_doc_id, detected_at, resolved, resolved_at, contradiction_type) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        c.id,
                        c.entity_id,
                        c.field_name,
                        c.old_value,
                        c.new_value,
                        c.source_doc_id,
                        c.detected_at.isoformat(),
                        int(c.resolved),
                        c.resolved_at.isoformat() if c.resolved_at else None,
                        c.contradiction_type.value,
                    ),
                )
        logger.info("contradiction.persisted", count=len(contradictions))

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    async def list_unresolved(self) -> list[Contradiction]:
        """Return all unresolved contradictions."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._list_sync, True)

    async def list_all(self) -> list[Contradiction]:
        """Return all contradictions (resolved and unresolved)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._list_sync, None)

    def _list_sync(self, only_unresolved: bool | None) -> list[Contradiction]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if only_unresolved is True:
                rows = conn.execute(
                    "SELECT * FROM contradictions WHERE resolved=0 ORDER BY detected_at DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM contradictions ORDER BY detected_at DESC"
                ).fetchall()
        return [self._row_to_contradiction(r) for r in rows]

    @staticmethod
    def _row_to_contradiction(row: sqlite3.Row) -> Contradiction:
        return Contradiction(
            id=row["id"],
            entity_id=row["entity_id"],
            field_name=row["field_name"],
            old_value=row["old_value"],
            new_value=row["new_value"],
            source_doc_id=row["source_doc_id"],
            detected_at=datetime.fromisoformat(row["detected_at"]),
            resolved=bool(row["resolved"]),
            resolved_at=(
                datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None
            ),
            contradiction_type=ContradictionType(row["contradiction_type"]),
        )

    async def resolve(self, contradiction_id: str) -> bool:
        """Mark a contradiction as resolved. Returns True if found."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._resolve_sync, contradiction_id)

    def _resolve_sync(self, contradiction_id: str) -> bool:
        now = datetime.now(tz=UTC).isoformat()
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                "UPDATE contradictions SET resolved=1, resolved_at=? WHERE id=?",
                (now, contradiction_id),
            )
            return cursor.rowcount > 0
