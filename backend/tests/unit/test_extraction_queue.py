"""Unit tests for ExtractionQueue.

Tests: enqueue, status, retry, persistence across restart.
Spec: F-006 FR-6
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nexuspkm.engine.extraction_queue import ExtractionQueue
from nexuspkm.models.contradiction import QueueStatus
from nexuspkm.models.document import Document, DocumentMetadata, SourceType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_document(doc_id: str = "doc-1") -> Document:
    now = datetime.now(tz=UTC)
    meta = DocumentMetadata(
        source_type=SourceType.OBSIDIAN_NOTE,
        source_id=doc_id,
        title="Test Document",
        created_at=now,
        updated_at=now,
        synced_at=now,
    )
    return Document(id=doc_id, content="Test content for extraction.", metadata=meta)


# ---------------------------------------------------------------------------
# Init / schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_creates_table(tmp_path: Path) -> None:
    queue = ExtractionQueue(tmp_path / "queue.db")
    await queue.init()

    conn = sqlite3.connect(tmp_path / "queue.db")
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    conn.close()

    assert "extraction_queue" in tables


@pytest.mark.asyncio
async def test_queue_init_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "queue.db"
    queue = ExtractionQueue(db_path)
    await queue.init()
    await queue.init()  # Should not raise


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_adds_pending_row(tmp_path: Path) -> None:
    queue = ExtractionQueue(tmp_path / "queue.db")
    await queue.init()

    doc = _make_document("doc-enqueue-1")
    await queue.enqueue(doc)

    status = await queue.status()
    assert status.pending == 1
    assert status.processing == 0
    assert status.done == 0
    assert status.failed == 0


@pytest.mark.asyncio
async def test_enqueue_multiple_documents(tmp_path: Path) -> None:
    queue = ExtractionQueue(tmp_path / "queue.db")
    await queue.init()

    for i in range(3):
        await queue.enqueue(_make_document(f"doc-multi-{i}"))

    status = await queue.status()
    assert status.pending == 3


@pytest.mark.asyncio
async def test_enqueue_same_document_twice_adds_two_rows(tmp_path: Path) -> None:
    """Queue is not idempotent — re-enqueuing the same doc is valid."""
    queue = ExtractionQueue(tmp_path / "queue.db")
    await queue.init()

    doc = _make_document("doc-dup")
    await queue.enqueue(doc)
    await queue.enqueue(doc)

    status = await queue.status()
    assert status.pending == 2


# ---------------------------------------------------------------------------
# Status counts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_returns_zero_counts_when_empty(tmp_path: Path) -> None:
    queue = ExtractionQueue(tmp_path / "queue.db")
    await queue.init()

    status = await queue.status()

    assert isinstance(status, QueueStatus)
    assert status.pending == 0
    assert status.processing == 0
    assert status.done == 0
    assert status.failed == 0


# ---------------------------------------------------------------------------
# Worker processes items
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_processes_pending_item(tmp_path: Path) -> None:
    queue = ExtractionQueue(tmp_path / "queue.db")
    await queue.init()

    doc = _make_document("doc-worker-1")
    await queue.enqueue(doc)

    pipeline = MagicMock()
    pipeline.process = AsyncMock(return_value=None)

    queue.start(pipeline, concurrency=1)
    await asyncio.sleep(0.2)
    await queue.stop()

    status = await queue.status()
    assert status.done == 1
    assert status.pending == 0
    assert pipeline.process.call_count == 1


@pytest.mark.asyncio
async def test_worker_marks_failed_on_exception(tmp_path: Path) -> None:
    queue = ExtractionQueue(tmp_path / "queue.db", _backoff_factor=0.01)
    await queue.init()

    doc = _make_document("doc-fail-1")
    await queue.enqueue(doc)

    pipeline = MagicMock()
    pipeline.process = AsyncMock(side_effect=RuntimeError("extraction failed"))

    queue.start(pipeline, concurrency=1)
    await asyncio.sleep(0.5)
    await queue.stop()

    status = await queue.status()
    # After 3 retries it should be failed
    assert status.failed == 1
    assert status.pending == 0


@pytest.mark.asyncio
async def test_worker_retries_before_failing(tmp_path: Path) -> None:
    queue = ExtractionQueue(tmp_path / "queue.db", _backoff_factor=0.01)
    await queue.init()

    doc = _make_document("doc-retry-1")
    await queue.enqueue(doc)

    call_count = 0

    async def flaky_process(d: Document) -> None:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("transient error")

    pipeline = MagicMock()
    pipeline.process = flaky_process

    queue.start(pipeline, concurrency=1)
    await asyncio.sleep(0.5)
    await queue.stop()

    status = await queue.status()
    assert status.done == 1
    assert call_count == 3


# ---------------------------------------------------------------------------
# Persistence across restart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_persists_across_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "queue.db"

    queue1 = ExtractionQueue(db_path)
    await queue1.init()
    await queue1.enqueue(_make_document("doc-persist-1"))
    await queue1.enqueue(_make_document("doc-persist-2"))

    # Simulate restart
    queue2 = ExtractionQueue(db_path)
    await queue2.init()

    status = await queue2.status()
    assert status.pending == 2


@pytest.mark.asyncio
async def test_processing_items_reset_to_pending_on_restart(tmp_path: Path) -> None:
    """Items stuck in 'processing' after a crash should be retryable."""
    db_path = tmp_path / "queue.db"
    queue1 = ExtractionQueue(db_path)
    await queue1.init()

    doc = _make_document("doc-stuck")
    await queue1.enqueue(doc)

    # Manually set to processing to simulate crashed worker
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE extraction_queue SET status='processing'")
    conn.commit()
    conn.close()

    queue2 = ExtractionQueue(db_path)
    await queue2.init()

    status = await queue2.status()
    # On init, processing items should be reset to pending
    assert status.pending == 1
    assert status.processing == 0
