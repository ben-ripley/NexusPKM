"""ProactiveService — notification persistence, meeting context assembly, related content detection.

Implements F-013 proactive context surfacing:
- SQLite-backed notification and preferences storage
- Meeting preparation context assembly via graph queries
- Related content detection (Jaccard similarity over shared entities)
- Contradiction notification bridging (polls ContradictionDetector)
- WebSocket broadcast manager
- APScheduler-based meeting scanner

Spec: F-013
NXP-87
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import WebSocket

from nexuspkm.engine.graph_store import GraphStore
from nexuspkm.models.document import Document
from nexuspkm.models.notification import (
    ActionItemSummary,
    DocumentSummary,
    MeetingContext,
    Notification,
    NotificationPreferences,
    NotificationPriority,
    NotificationType,
    RelatedContentAlert,
)
from nexuspkm.models.schedule import PersonSummary
from nexuspkm.providers.base import BaseLLMProvider

if TYPE_CHECKING:
    from nexuspkm.engine.contradiction import ContradictionDetector

logger = structlog.get_logger(__name__)

_NOTIFICATIONS_DDL = """\
CREATE TABLE IF NOT EXISTS notifications (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL,
    title           TEXT NOT NULL,
    summary         TEXT NOT NULL,
    priority        TEXT NOT NULL,
    data            TEXT NOT NULL DEFAULT '{}',
    read            INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);
"""

_PREFERENCES_DDL = """\
CREATE TABLE IF NOT EXISTS notification_preferences (
    id                              INTEGER PRIMARY KEY CHECK (id = 1),
    meeting_prep_enabled            INTEGER NOT NULL DEFAULT 1,
    meeting_prep_lead_time_minutes  INTEGER NOT NULL DEFAULT 60,
    related_content_enabled         INTEGER NOT NULL DEFAULT 1,
    related_content_threshold       REAL    NOT NULL DEFAULT 0.7,
    contradiction_alerts_enabled    INTEGER NOT NULL DEFAULT 1,
    webhook_url                     TEXT
);
INSERT OR IGNORE INTO notification_preferences (id) VALUES (1);
"""


class NotificationWSManager:
    """Manages active WebSocket connections for push notifications."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    async def broadcast(self, notification: Notification) -> None:
        payload = notification.model_dump_json()
        dead: set[WebSocket] = set()
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._connections.discard(ws)


class ProactiveService:
    """Owns notification persistence, context assembly, and background scanning."""

    def __init__(
        self,
        graph_store: GraphStore,
        llm_provider: BaseLLMProvider,
        db_path: Path,
        scan_interval_seconds: int = 900,
    ) -> None:
        self._graph = graph_store
        self._llm = llm_provider
        self._db_path = db_path
        self._scan_interval = scan_interval_seconds
        self._scheduler: AsyncIOScheduler | None = None
        self._contradiction_detector: ContradictionDetector | None = None
        self.ws_manager = NotificationWSManager()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def init(self) -> None:
        """Create SQLite schema (idempotent). Call once at startup."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._ensure_schema)

    def _ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.executescript(_NOTIFICATIONS_DDL)
            conn.executescript(_PREFERENCES_DDL)

    def start_scanner(
        self,
        contradiction_detector: ContradictionDetector | None = None,
    ) -> None:
        """Start the APScheduler meeting scanner. Safe to call multiple times."""
        self._contradiction_detector = contradiction_detector
        if self._scheduler is not None and self._scheduler.running:
            return
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self._scan_tick,
            "interval",
            seconds=self._scan_interval,
            id="proactive_scan",
            replace_existing=True,
        )
        scheduler.start()
        self._scheduler = scheduler
        logger.info("proactive_scanner_started", interval_seconds=self._scan_interval)

    async def shutdown(self) -> None:
        """Stop the scanner gracefully."""
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    # ------------------------------------------------------------------
    # Periodic scan tick
    # ------------------------------------------------------------------

    async def _scan_tick(self) -> None:
        """Runs every scan interval: check for upcoming meetings + contradiction polling."""
        logger.debug("proactive_scan_tick")
        try:
            await self._scan_upcoming_meetings()
        except Exception:
            logger.exception("proactive_scan.meeting_scan_error")
        if self._contradiction_detector is not None:
            try:
                await self.poll_contradictions(self._contradiction_detector)
            except Exception:
                logger.exception("proactive_scan.contradiction_poll_error")

    async def _scan_upcoming_meetings(self) -> None:
        """Find meetings within lead_time window and emit meeting_prep notifications."""
        prefs = await self.get_preferences()
        if not prefs.meeting_prep_enabled:
            return

        loop = asyncio.get_running_loop()
        now = datetime.now(tz=UTC)
        window_end = now + timedelta(minutes=prefs.meeting_prep_lead_time_minutes)

        meetings = await loop.run_in_executor(
            None, self._fetch_upcoming_meetings_sync, now, window_end
        )

        for meeting in meetings:
            notif_id = f"meeting_prep_{meeting['id']}"
            exists = await loop.run_in_executor(None, self._notification_exists_sync, notif_id)
            if exists:
                continue

            ctx = await self.get_meeting_context(meeting["id"])
            summary_parts = []
            if ctx:
                if ctx.attendees:
                    names = ", ".join(a.name for a in ctx.attendees[:3])
                    summary_parts.append(f"Attendees: {names}")
                if ctx.open_action_items:
                    summary_parts.append(f"{len(ctx.open_action_items)} open action items")

            notif = Notification(
                id=notif_id,
                type=NotificationType.MEETING_PREP,
                title=f"Upcoming: {meeting.get('title', 'Meeting')}",
                summary="; ".join(summary_parts) or "Meeting starting soon",
                priority=NotificationPriority.HIGH,
                data={"meeting_id": meeting["id"]},
                created_at=datetime.now(tz=UTC),
            )
            await self.save_notification(notif)
            await self.ws_manager.broadcast(notif)
            await self._deliver_webhook(notif, prefs)

    def _fetch_upcoming_meetings_sync(
        self, now: datetime, window_end: datetime
    ) -> list[dict[str, Any]]:
        rows = self._graph.execute(
            "MATCH (m:Meeting) "
            "WHERE m.date >= $now AND m.date <= $window_end "
            "RETURN m.id AS id, m.title AS title, m.date AS date",
            {"now": now, "window_end": window_end},
        )
        return list(rows)

    def _notification_exists_sync(self, notif_id: str) -> bool:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute("SELECT 1 FROM notifications WHERE id = ?", (notif_id,)).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # on_insert hook
    # ------------------------------------------------------------------

    async def on_document_ingested(self, doc: Document) -> None:
        """Called after every KnowledgeIndex.insert(). Runs related-content detection."""
        prefs = await self.get_preferences()
        if not prefs.related_content_enabled:
            return
        try:
            loop = asyncio.get_running_loop()
            alert = await loop.run_in_executor(
                None,
                self._detect_related_content_sync,
                doc.id,
                prefs.related_content_threshold,
            )
            if alert is not None:
                notif = Notification(
                    id=f"related_{doc.id}",
                    type=NotificationType.RELATED_CONTENT,
                    title=f"Related content: {doc.metadata.title}",
                    summary=alert.summary,
                    priority=NotificationPriority.LOW,
                    data={
                        "new_doc_id": doc.id,
                        "related_doc_ids": [d.id for d in alert.related_documents],
                        "connection_strength": alert.connection_strength,
                    },
                    created_at=datetime.now(tz=UTC),
                )
                await self.save_notification(notif)
                await self.ws_manager.broadcast(notif)
                await self._deliver_webhook(notif, prefs)
        except Exception:
            logger.exception("proactive.on_document_ingested_error", doc_id=doc.id)

    # ------------------------------------------------------------------
    # Related content detection (sync — run in executor)
    # ------------------------------------------------------------------

    def _detect_related_content_sync(
        self, doc_id: str, threshold: float
    ) -> RelatedContentAlert | None:
        """Find documents that share entities with doc_id above the Jaccard threshold."""
        entity_rows = self._graph.execute(
            "MATCH (d:Document {id: $did})-[r]-(e) "
            "WHERE e.__label__ IN ['Person', 'Topic', 'Project'] "
            "RETURN DISTINCT e.id AS entity_id",
            {"did": doc_id},
        )
        new_entities: set[str] = {r["entity_id"] for r in entity_rows if r.get("entity_id")}
        if not new_entities:
            return None

        related_rows = self._graph.execute(
            "MATCH (d2:Document)-[r2]-(e2) "
            "WHERE e2.id IN $entity_ids AND d2.id <> $did "
            "RETURN DISTINCT d2.id AS doc_id, d2.title AS title, "
            "       d2.source_type AS source_type, e2.id AS entity_id",
            {"entity_ids": list(new_entities), "did": doc_id},
        )

        related_doc_entities: dict[str, set[str]] = defaultdict(set)
        related_doc_meta: dict[str, dict[str, str]] = {}
        for row in related_rows:
            rdid = row.get("doc_id")
            if rdid:
                related_doc_entities[rdid].add(row["entity_id"])
                related_doc_meta[rdid] = {
                    "title": row.get("title") or "",
                    "source_type": row.get("source_type") or "document",
                }

        best_score = 0.0
        best_docs: list[DocumentSummary] = []
        for rdid, r_entities in related_doc_entities.items():
            score = self._jaccard(new_entities, r_entities)
            if score >= threshold:
                best_docs.append(
                    DocumentSummary(
                        id=rdid,
                        title=related_doc_meta[rdid]["title"],
                        source_type=related_doc_meta[rdid]["source_type"],
                    )
                )
                best_score = max(best_score, score)

        if not best_docs:
            return None

        return RelatedContentAlert(
            new_document=DocumentSummary(id=doc_id, title="", source_type="document"),
            related_documents=best_docs[:5],
            connection_type="same_topic",
            connection_strength=round(best_score, 3),
            summary=f"Connected to {len(best_docs)} existing document(s) via shared entities",
        )

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        """Jaccard similarity between two entity sets."""
        if not a and not b:
            return 0.0
        union = len(a | b)
        if union == 0:
            return 0.0
        return len(a & b) / union

    # ------------------------------------------------------------------
    # Contradiction notification bridging
    # ------------------------------------------------------------------

    async def poll_contradictions(self, detector: ContradictionDetector) -> None:
        """Create CONTRADICTION notifications for any unresolved contradictions without one."""
        prefs = await self.get_preferences()
        if not prefs.contradiction_alerts_enabled:
            return

        contradictions = await detector.list_unresolved()
        loop = asyncio.get_running_loop()
        for c in contradictions:
            notif_id = f"contradiction_{c.id}"
            exists = await loop.run_in_executor(None, self._notification_exists_sync, notif_id)
            if exists:
                continue

            notif = Notification(
                id=notif_id,
                type=NotificationType.CONTRADICTION,
                title=f"Contradiction: {c.field_name} on entity {c.entity_id}",
                summary=(f"Field '{c.field_name}' changed from '{c.old_value}' to '{c.new_value}'"),
                priority=NotificationPriority.MEDIUM,
                data={
                    "contradiction_id": c.id,
                    "entity_id": c.entity_id,
                    "field_name": c.field_name,
                },
                created_at=datetime.now(tz=UTC),
            )
            await self.save_notification(notif)
            await self.ws_manager.broadcast(notif)
            await self._deliver_webhook(notif, prefs)

    # ------------------------------------------------------------------
    # Meeting context assembly
    # ------------------------------------------------------------------

    async def get_meeting_context(self, meeting_id: str) -> MeetingContext | None:
        """Assemble full meeting prep context from the graph."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._assemble_meeting_context_sync, meeting_id)

    def _assemble_meeting_context_sync(self, meeting_id: str) -> MeetingContext | None:
        meeting_rows = self._graph.execute(
            "MATCH (m:Meeting {id: $mid}) RETURN m.id AS id, m.title AS title, m.date AS date",
            {"mid": meeting_id},
        )
        if not meeting_rows:
            return None

        m_row = meeting_rows[0]
        meeting_title = m_row.get("title") or ""
        meeting_time: datetime | None = m_row.get("date")
        if meeting_time is not None and meeting_time.tzinfo is None:
            meeting_time = meeting_time.replace(tzinfo=UTC)

        attendee_rows = self._graph.execute(
            "MATCH (p:Person)-[:ATTENDED]->(m:Meeting {id: $mid}) "
            "RETURN p.id AS id, p.name AS name, p.email AS email",
            {"mid": meeting_id},
        )
        attendees = [
            PersonSummary(
                id=r["id"],
                name=r.get("name") or "",
                email=r.get("email") or "",
            )
            for r in attendee_rows
        ]
        attendee_ids = [a.id for a in attendees]

        prev_rows = self._graph.execute(
            "MATCH (p:Person)-[:ATTENDED]->(m2:Meeting) "
            "WHERE p.id IN $attendee_ids AND m2.id <> $mid "
            "RETURN DISTINCT m2.id AS doc_id, m2.title AS title, m2.date AS created_at",
            {"attendee_ids": attendee_ids, "mid": meeting_id},
        )
        previous_meetings = [self._row_to_doc_summary(r, "teams") for r in prev_rows]

        doc_rows = self._graph.execute(
            "MATCH (p:Person)-[:MENTIONED_IN]->(d:Document) "
            "WHERE p.id IN $attendee_ids "
            "RETURN DISTINCT d.id AS doc_id, d.title AS title, "
            "       d.source_type AS source_type, d.created_at AS created_at",
            {"attendee_ids": attendee_ids},
        )
        related_tickets = [
            self._row_to_doc_summary(r)
            for r in doc_rows
            if r.get("source_type") in ("jira", "ticket", "jira_issue")
        ]
        related_notes = [
            self._row_to_doc_summary(r)
            for r in doc_rows
            if r.get("source_type")
            in ("obsidian", "apple_notes", "note", "obsidian_note", "apple_note")
        ]
        related_emails = [
            self._row_to_doc_summary(r)
            for r in doc_rows
            if r.get("source_type") in ("outlook", "email", "outlook_email")
        ]

        ai_rows = self._graph.execute(
            "MATCH (a:ActionItem)-[:ASSIGNED_TO]->(p:Person) "
            "WHERE p.id IN $attendee_ids AND a.status = 'open' "
            "RETURN a.id AS id, a.description AS description, "
            "       a.status AS status, p.name AS assignee_name",
            {"attendee_ids": attendee_ids},
        )
        open_action_items = [
            ActionItemSummary(
                id=r["id"],
                description=r.get("description") or "",
                status=r.get("status") or "open",
                assignee_name=r.get("assignee_name") or "",
            )
            for r in ai_rows
        ]

        return MeetingContext(
            meeting_id=meeting_id,
            meeting_title=meeting_title,
            meeting_time=meeting_time,
            attendees=attendees,
            previous_meetings=previous_meetings[:5],
            related_tickets=related_tickets[:10],
            related_notes=related_notes[:10],
            related_emails=related_emails[:10],
            open_action_items=open_action_items[:10],
            suggested_agenda=[],
        )

    # ------------------------------------------------------------------
    # Notification CRUD (async public API)
    # ------------------------------------------------------------------

    async def save_notification(self, notification: Notification) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._save_sync, notification)

    def _save_sync(self, n: Notification) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO notifications "
                "(id, type, title, summary, priority, data, read, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    n.id,
                    n.type.value,
                    n.title,
                    n.summary,
                    n.priority.value,
                    json.dumps(n.data),
                    int(n.read),
                    n.created_at.isoformat(),
                ),
            )

    async def list_notifications(
        self,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._list_sync, unread_only, limit, offset)

    def _list_sync(self, unread_only: bool, limit: int, offset: int) -> list[Notification]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if unread_only:
                rows = conn.execute(
                    "SELECT * FROM notifications WHERE read=0 "
                    "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
        return [self._row_to_notification(r) for r in rows]

    async def get_unread_count(self) -> int:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._unread_count_sync)

    def _unread_count_sync(self) -> int:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute("SELECT count(*) FROM notifications WHERE read=0").fetchone()
        return int(row[0]) if row else 0

    async def mark_read(self, notification_id: str) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._mark_read_sync, notification_id)

    def _mark_read_sync(self, notification_id: str) -> bool:
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute("UPDATE notifications SET read=1 WHERE id=?", (notification_id,))
        return cursor.rowcount > 0

    async def dismiss(self, notification_id: str) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._dismiss_sync, notification_id)

    def _dismiss_sync(self, notification_id: str) -> bool:
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute("DELETE FROM notifications WHERE id=?", (notification_id,))
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Preferences (async public API)
    # ------------------------------------------------------------------

    async def get_preferences(self) -> NotificationPreferences:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_prefs_sync)

    def _get_prefs_sync(self) -> NotificationPreferences:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM notification_preferences WHERE id=1").fetchone()
        if row is None:
            return NotificationPreferences()
        return NotificationPreferences(
            meeting_prep_enabled=bool(row["meeting_prep_enabled"]),
            meeting_prep_lead_time_minutes=int(row["meeting_prep_lead_time_minutes"]),
            related_content_enabled=bool(row["related_content_enabled"]),
            related_content_threshold=float(row["related_content_threshold"]),
            contradiction_alerts_enabled=bool(row["contradiction_alerts_enabled"]),
            webhook_url=row["webhook_url"],
        )

    async def save_preferences(self, prefs: NotificationPreferences) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._save_prefs_sync, prefs)

    def _save_prefs_sync(self, prefs: NotificationPreferences) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO notification_preferences "
                "(id, meeting_prep_enabled, meeting_prep_lead_time_minutes, "
                " related_content_enabled, related_content_threshold, "
                " contradiction_alerts_enabled, webhook_url) "
                "VALUES (1, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "  meeting_prep_enabled=excluded.meeting_prep_enabled, "
                "  meeting_prep_lead_time_minutes=excluded.meeting_prep_lead_time_minutes, "
                "  related_content_enabled=excluded.related_content_enabled, "
                "  related_content_threshold=excluded.related_content_threshold, "
                "  contradiction_alerts_enabled=excluded.contradiction_alerts_enabled, "
                "  webhook_url=excluded.webhook_url",
                (
                    int(prefs.meeting_prep_enabled),
                    prefs.meeting_prep_lead_time_minutes,
                    int(prefs.related_content_enabled),
                    prefs.related_content_threshold,
                    int(prefs.contradiction_alerts_enabled),
                    prefs.webhook_url,
                ),
            )

    # ------------------------------------------------------------------
    # Webhook delivery
    # ------------------------------------------------------------------

    async def _deliver_webhook(
        self, notification: Notification, prefs: NotificationPreferences
    ) -> None:
        if not prefs.webhook_url:
            return
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    prefs.webhook_url,
                    json=notification.model_dump(mode="json"),
                )
        except Exception:
            logger.warning(
                "proactive.webhook_delivery_failed",
                notification_id=notification.id,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_doc_summary(
        row: dict[str, Any], default_source: str = "document"
    ) -> DocumentSummary:
        created_at: datetime | None = row.get("created_at")
        if (
            created_at is not None
            and isinstance(created_at, datetime)
            and created_at.tzinfo is None
        ):
            created_at = created_at.replace(tzinfo=UTC)
        return DocumentSummary(
            id=row.get("doc_id") or row.get("id") or "",
            title=row.get("title") or "",
            source_type=row.get("source_type") or default_source,
            created_at=created_at,
        )

    @staticmethod
    def _row_to_notification(row: sqlite3.Row) -> Notification:
        return Notification(
            id=row["id"],
            type=NotificationType(row["type"]),
            title=row["title"],
            summary=row["summary"],
            priority=NotificationPriority(row["priority"]),
            data=json.loads(row["data"]),
            read=bool(row["read"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
