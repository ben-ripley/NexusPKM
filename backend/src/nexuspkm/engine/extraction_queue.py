"""ExtractionQueue — persistent SQLite-backed FIFO queue for entity extraction.

Documents are enqueued after successful ingestion and processed asynchronously
by background worker tasks. The queue survives application restarts.

Spec: F-006 FR-6
"""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from nexuspkm.models.contradiction import QueueStatus
from nexuspkm.models.document import Document

if TYPE_CHECKING:
    from nexuspkm.engine.entity_pipeline import EntityExtractionPipeline

logger = structlog.get_logger(__name__)

_SCHEMA_DDL = """\
CREATE TABLE IF NOT EXISTS extraction_queue (
    id            TEXT PRIMARY KEY,
    document_id   TEXT NOT NULL,
    document_json TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    retry_count   INTEGER NOT NULL DEFAULT 0,
    enqueued_at   TEXT NOT NULL,
    attempted_at  TEXT,
    error         TEXT
);
"""

_MAX_RETRIES = 3
_POLL_INTERVAL = 0.05  # seconds between DB polls when queue is empty


class ExtractionQueue:
    """SQLite-backed persistent queue for background entity extraction.

    Worker lifecycle:
    - ``init()``  — create tables, reset stale 'processing' rows to 'pending'
    - ``start(pipeline, concurrency)`` — spawn asyncio tasks to consume the queue
    - ``stop()``  — signal workers to stop and await completion
    """

    def __init__(self, db_path: Path, _backoff_factor: float = 1.0) -> None:
        self._db_path = db_path
        self._shutdown = asyncio.Event()
        self._workers: list[asyncio.Task[None]] = []
        self._backoff_factor = _backoff_factor

    async def init(self) -> None:
        """Create tables and reset stale 'processing' rows to 'pending'."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._init_sync)

    def _init_sync(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.executescript(_SCHEMA_DDL)
            # Reset any rows stuck in 'processing' from a previous crash
            conn.execute("UPDATE extraction_queue SET status='pending' WHERE status='processing'")

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------

    async def enqueue(self, document: Document) -> None:
        """Insert a document into the queue with status='pending'."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._enqueue_sync, document)

    def _enqueue_sync(self, document: Document) -> None:
        row_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC).isoformat()
        doc_json = document.model_dump_json()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO extraction_queue "
                "(id, document_id, document_json, status, retry_count, enqueued_at) "
                "VALUES (?,?,?,?,?,?)",
                (row_id, document.id, doc_json, "pending", 0, now),
            )
        logger.debug("extraction_queue.enqueued", document_id=document.id, row_id=row_id)

    # ------------------------------------------------------------------
    # Worker lifecycle
    # ------------------------------------------------------------------

    def start(self, pipeline: EntityExtractionPipeline, concurrency: int = 2) -> None:
        """Spawn background asyncio Tasks to consume the queue."""
        self._shutdown.clear()
        for i in range(concurrency):
            task = asyncio.create_task(
                self._worker(pipeline, worker_id=i),
                name=f"extraction-worker-{i}",
            )
            self._workers.append(task)
        logger.info("extraction_queue.started", concurrency=concurrency)

    async def stop(self) -> None:
        """Signal workers to stop and await completion."""
        self._shutdown.set()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers.clear()
        logger.info("extraction_queue.stopped")

    # ------------------------------------------------------------------
    # Worker loop
    # ------------------------------------------------------------------

    async def _worker(self, pipeline: EntityExtractionPipeline, worker_id: int) -> None:
        log = logger.bind(worker_id=worker_id)
        log.debug("extraction_worker.started")

        while not self._shutdown.is_set():
            row = await self._claim_next()
            if row is None:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._shutdown.wait(), timeout=_POLL_INTERVAL)
                continue

            row_id, doc_json, retry_count = row
            try:
                document = Document.model_validate_json(doc_json)
                await pipeline.process(document)
                await self._mark_done(row_id)
                log.info("extraction_worker.done", row_id=row_id)
            except Exception as exc:
                new_retry = retry_count + 1
                log.warning(
                    "extraction_worker.failed",
                    row_id=row_id,
                    retry=new_retry,
                    error=str(exc),
                )
                if new_retry >= _MAX_RETRIES:
                    await self._mark_failed(row_id, str(exc))
                else:
                    backoff = (2**retry_count) * self._backoff_factor
                    await self._reschedule(row_id, new_retry, str(exc), backoff)

        log.debug("extraction_worker.stopped")

    # ------------------------------------------------------------------
    # DB operations
    # ------------------------------------------------------------------

    async def _claim_next(self) -> tuple[str, str, int] | None:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._claim_next_sync)

    def _claim_next_sync(self) -> tuple[str, str, int] | None:
        now = datetime.now(tz=UTC).isoformat()
        # Use isolation_level=None (autocommit) so we can issue BEGIN IMMEDIATE
        # explicitly, preventing two concurrent workers from claiming the same row.
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(self._db_path, isolation_level=None)
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT id, document_json, retry_count FROM extraction_queue "
                "WHERE status='pending' ORDER BY enqueued_at ASC LIMIT 1"
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                return None
            row_id, doc_json, retry_count = row
            conn.execute(
                "UPDATE extraction_queue SET status='processing', attempted_at=? WHERE id=?",
                (now, row_id),
            )
            conn.execute("COMMIT")
        except Exception:
            if conn is not None:
                conn.execute("ROLLBACK")
            raise
        finally:
            if conn is not None:
                conn.close()
        return row_id, doc_json, retry_count

    async def _mark_done(self, row_id: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self._update_status(row_id, "done", error=None, retry_count=None),
        )

    async def _mark_failed(self, row_id: str, error: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self._update_status(row_id, "failed", error=error, retry_count=None),
        )

    async def _reschedule(
        self, row_id: str, retry_count: int, error: str, backoff_secs: float
    ) -> None:
        await asyncio.sleep(backoff_secs)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self._update_status(row_id, "pending", error=error, retry_count=retry_count),
        )

    def _update_status(
        self,
        row_id: str,
        status: str,
        error: str | None,
        retry_count: int | None,
    ) -> None:
        with sqlite3.connect(self._db_path) as conn:
            if retry_count is not None:
                conn.execute(
                    "UPDATE extraction_queue SET status=?, error=?, retry_count=? WHERE id=?",
                    (status, error, retry_count, row_id),
                )
            else:
                conn.execute(
                    "UPDATE extraction_queue SET status=?, error=? WHERE id=?",
                    (status, error, row_id),
                )

    # ------------------------------------------------------------------
    # Status query
    # ------------------------------------------------------------------

    async def status(self) -> QueueStatus:
        """Return counts by status."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._status_sync)

    def _status_sync(self) -> QueueStatus:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) FROM extraction_queue GROUP BY status"
            ).fetchall()
        counts: dict[str, int] = {r[0]: r[1] for r in rows}
        return QueueStatus(
            pending=counts.get("pending", 0),
            processing=counts.get("processing", 0),
            done=counts.get("done", 0),
            failed=counts.get("failed", 0),
        )
