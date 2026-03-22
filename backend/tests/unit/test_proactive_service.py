"""Unit tests for ProactiveService — notification CRUD, preferences, scoring.

Spec: F-013
NXP-87
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexuspkm.engine.graph_store import GraphStore
from nexuspkm.models.document import Document, DocumentMetadata, SourceType
from nexuspkm.models.notification import (
    Notification,
    NotificationPreferences,
    NotificationPriority,
    NotificationType,
)
from nexuspkm.providers.base import BaseLLMProvider
from nexuspkm.services.proactive import ProactiveService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_document(doc_id: str = "doc-1", title: str = "Test Doc") -> Document:
    now = datetime.now(tz=UTC)
    return Document(
        id=doc_id,
        content="Test content",
        metadata=DocumentMetadata(
            source_type=SourceType.OBSIDIAN_NOTE,
            source_id=doc_id,
            title=title,
            created_at=now,
            updated_at=now,
            synced_at=now,
        ),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_graph() -> MagicMock:
    return MagicMock(spec=GraphStore)


@pytest.fixture
def mock_llm() -> MagicMock:
    return MagicMock(spec=BaseLLMProvider)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "notifications.db"


@pytest.fixture
async def service(
    mock_graph: MagicMock,
    mock_llm: MagicMock,
    db_path: Path,
) -> ProactiveService:
    svc = ProactiveService(mock_graph, mock_llm, db_path)
    await svc.init()
    return svc


def _make_notification(
    nid: str = "n-1",
    ntype: NotificationType = NotificationType.INSIGHT,
    read: bool = False,
) -> Notification:
    return Notification(
        id=nid,
        type=ntype,
        title="Test notification",
        summary="A summary",
        priority=NotificationPriority.MEDIUM,
        data={},
        read=read,
        created_at=datetime.now(tz=UTC),
    )


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_creates_tables(
    db_path: Path, mock_graph: MagicMock, mock_llm: MagicMock
) -> None:
    svc = ProactiveService(mock_graph, mock_llm, db_path)
    await svc.init()
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "notifications" in tables
    assert "notification_preferences" in tables


# ---------------------------------------------------------------------------
# Notification CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_list_notification(service: ProactiveService) -> None:
    n = _make_notification("n-1")
    await service.save_notification(n)
    results = await service.list_notifications()
    assert len(results) == 1
    assert results[0].id == "n-1"


@pytest.mark.asyncio
async def test_list_unread_only(service: ProactiveService) -> None:
    await service.save_notification(_make_notification("n-1", read=False))
    await service.save_notification(_make_notification("n-2", read=True))
    unread = await service.list_notifications(unread_only=True)
    assert len(unread) == 1
    assert unread[0].id == "n-1"


@pytest.mark.asyncio
async def test_list_with_limit(service: ProactiveService) -> None:
    for i in range(5):
        await service.save_notification(_make_notification(f"n-{i}"))
    results = await service.list_notifications(limit=3)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_unread_count(service: ProactiveService) -> None:
    await service.save_notification(_make_notification("n-1", read=False))
    await service.save_notification(_make_notification("n-2", read=False))
    await service.save_notification(_make_notification("n-3", read=True))
    count = await service.get_unread_count()
    assert count == 2


@pytest.mark.asyncio
async def test_mark_read(service: ProactiveService) -> None:
    await service.save_notification(_make_notification("n-1", read=False))
    result = await service.mark_read("n-1")
    assert result is True
    count = await service.get_unread_count()
    assert count == 0


@pytest.mark.asyncio
async def test_mark_read_missing_returns_false(service: ProactiveService) -> None:
    result = await service.mark_read("does-not-exist")
    assert result is False


@pytest.mark.asyncio
async def test_dismiss_notification(service: ProactiveService) -> None:
    await service.save_notification(_make_notification("n-1"))
    result = await service.dismiss("n-1")
    assert result is True
    results = await service.list_notifications()
    assert len(results) == 0


@pytest.mark.asyncio
async def test_dismiss_missing_returns_false(service: ProactiveService) -> None:
    result = await service.dismiss("does-not-exist")
    assert result is False


@pytest.mark.asyncio
async def test_no_duplicate_notifications(service: ProactiveService) -> None:
    n = _make_notification("n-1")
    await service.save_notification(n)
    await service.save_notification(n)  # duplicate
    results = await service.list_notifications()
    assert len(results) == 1


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_preferences(service: ProactiveService) -> None:
    prefs = await service.get_preferences()
    assert prefs.meeting_prep_enabled is True
    assert prefs.related_content_enabled is True
    assert prefs.contradiction_alerts_enabled is True
    assert prefs.webhook_url is None


@pytest.mark.asyncio
async def test_update_preferences(service: ProactiveService) -> None:
    updated = NotificationPreferences(
        meeting_prep_enabled=False,
        meeting_prep_lead_time_minutes=30,
        related_content_threshold=0.5,
        webhook_url="http://example.com/hook",
    )
    await service.save_preferences(updated)
    loaded = await service.get_preferences()
    assert loaded.meeting_prep_enabled is False
    assert loaded.meeting_prep_lead_time_minutes == 30
    assert loaded.webhook_url == "http://example.com/hook"


@pytest.mark.asyncio
async def test_preferences_persist_across_reinit(
    mock_graph: MagicMock,
    mock_llm: MagicMock,
    db_path: Path,
) -> None:
    svc1 = ProactiveService(mock_graph, mock_llm, db_path)
    await svc1.init()
    await svc1.save_preferences(NotificationPreferences(meeting_prep_enabled=False))

    svc2 = ProactiveService(mock_graph, mock_llm, db_path)
    await svc2.init()
    prefs = await svc2.get_preferences()
    assert prefs.meeting_prep_enabled is False


# ---------------------------------------------------------------------------
# Jaccard scoring for related content
# ---------------------------------------------------------------------------


def test_jaccard_score_full_overlap() -> None:
    assert ProactiveService._jaccard({"a", "b", "c"}, {"a", "b", "c"}) == pytest.approx(1.0)


def test_jaccard_score_no_overlap() -> None:
    assert ProactiveService._jaccard({"a", "b"}, {"c", "d"}) == pytest.approx(0.0)


def test_jaccard_score_partial_overlap() -> None:
    score = ProactiveService._jaccard({"a", "b", "c"}, {"b", "c", "d"})
    # intersection={b,c}=2, union={a,b,c,d}=4 → 0.5
    assert score == pytest.approx(0.5)


def test_jaccard_empty_sets() -> None:
    assert ProactiveService._jaccard(set(), set()) == 0.0


def test_jaccard_one_empty() -> None:
    assert ProactiveService._jaccard({"a"}, set()) == 0.0


# ---------------------------------------------------------------------------
# on_document_ingested (related content detection)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_document_ingested_calls_detect_sync(
    service: ProactiveService,
) -> None:
    doc = _make_document("doc-new")
    prefs = NotificationPreferences(related_content_threshold=0.0)
    await service.save_preferences(prefs)

    with patch.object(service, "_detect_related_content_sync", return_value=None) as mock_detect:
        await service.on_document_ingested(doc)
        mock_detect.assert_called_once_with("doc-new", 0.0)


@pytest.mark.asyncio
async def test_on_document_ingested_skipped_when_disabled(
    service: ProactiveService,
) -> None:
    prefs = NotificationPreferences(related_content_enabled=False)
    await service.save_preferences(prefs)
    doc = _make_document("doc-new")

    with patch.object(service, "_detect_related_content_sync") as mock_detect:
        await service.on_document_ingested(doc)
        mock_detect.assert_not_called()


@pytest.mark.asyncio
async def test_on_document_ingested_creates_notification_when_alert(
    service: ProactiveService,
) -> None:
    from nexuspkm.models.notification import DocumentSummary, RelatedContentAlert

    doc = _make_document("doc-new", title="New Doc")
    alert = RelatedContentAlert(
        new_document=DocumentSummary(id="doc-new", title="New Doc", source_type="obsidian_note"),
        related_documents=[
            DocumentSummary(id="doc-old", title="Old Doc", source_type="obsidian_note")
        ],
        connection_type="same_topic",
        connection_strength=0.8,
        summary="Connected to 1 existing document(s) via shared entities",
    )

    with patch.object(service, "_detect_related_content_sync", return_value=alert):
        await service.on_document_ingested(doc)

    notifications = await service.list_notifications()
    assert len(notifications) == 1
    assert notifications[0].type == NotificationType.RELATED_CONTENT


# ---------------------------------------------------------------------------
# Contradiction notification bridging
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_contradictions_creates_notification(
    service: ProactiveService,
) -> None:
    from nexuspkm.models.contradiction import Contradiction, ContradictionType

    contradiction = Contradiction(
        id="c-1",
        entity_id="e-1",
        field_name="status",
        old_value="open",
        new_value="closed",
        source_doc_id="doc-1",
        detected_at=datetime.now(tz=UTC),
        contradiction_type=ContradictionType.STATUS_CONFLICT,
    )

    mock_detector = MagicMock()
    mock_detector.list_unresolved = AsyncMock(return_value=[contradiction])

    await service.poll_contradictions(mock_detector)

    notifications = await service.list_notifications()
    assert len(notifications) == 1
    assert notifications[0].type == NotificationType.CONTRADICTION


@pytest.mark.asyncio
async def test_poll_contradictions_no_duplicates(
    service: ProactiveService,
) -> None:
    from nexuspkm.models.contradiction import Contradiction, ContradictionType

    contradiction = Contradiction(
        id="c-1",
        entity_id="e-1",
        field_name="status",
        old_value="open",
        new_value="closed",
        source_doc_id="doc-1",
        detected_at=datetime.now(tz=UTC),
        contradiction_type=ContradictionType.STATUS_CONFLICT,
    )

    mock_detector = MagicMock()
    mock_detector.list_unresolved = AsyncMock(return_value=[contradiction])

    await service.poll_contradictions(mock_detector)
    await service.poll_contradictions(mock_detector)  # second call — no duplicate

    notifications = await service.list_notifications()
    assert len(notifications) == 1


@pytest.mark.asyncio
async def test_poll_contradictions_skipped_when_disabled(
    service: ProactiveService,
) -> None:
    prefs = NotificationPreferences(contradiction_alerts_enabled=False)
    await service.save_preferences(prefs)

    mock_detector = MagicMock()
    mock_detector.list_unresolved = AsyncMock(return_value=[])

    await service.poll_contradictions(mock_detector)
    mock_detector.list_unresolved.assert_not_called()
