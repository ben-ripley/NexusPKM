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


# ---------------------------------------------------------------------------
# Background scanner: _scan_upcoming_meetings / _scan_tick
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_upcoming_meetings_creates_notification(
    service: ProactiveService,
) -> None:
    from datetime import timedelta

    now = datetime.now(tz=UTC)
    meeting = {"id": "m-1", "title": "Sprint Review", "date": now + timedelta(minutes=30)}
    service._graph.execute = MagicMock(return_value=[meeting])

    with patch.object(service, "get_meeting_context", new_callable=AsyncMock, return_value=None):
        await service._scan_upcoming_meetings()

    notifications = await service.list_notifications()
    assert len(notifications) == 1
    assert notifications[0].id == "meeting_prep_m-1"
    assert notifications[0].type == NotificationType.MEETING_PREP


@pytest.mark.asyncio
async def test_scan_upcoming_meetings_no_duplicates(
    service: ProactiveService,
) -> None:
    from datetime import timedelta

    now = datetime.now(tz=UTC)
    meeting = {"id": "m-1", "title": "Sprint Review", "date": now + timedelta(minutes=30)}
    service._graph.execute = MagicMock(return_value=[meeting])

    with patch.object(service, "get_meeting_context", new_callable=AsyncMock, return_value=None):
        await service._scan_upcoming_meetings()
        await service._scan_upcoming_meetings()  # second call — no duplicate

    notifications = await service.list_notifications()
    assert len(notifications) == 1


@pytest.mark.asyncio
async def test_scan_upcoming_meetings_skipped_when_disabled(
    service: ProactiveService,
) -> None:
    prefs = NotificationPreferences(meeting_prep_enabled=False)
    await service.save_preferences(prefs)

    service._graph.execute = MagicMock(return_value=[])

    await service._scan_upcoming_meetings()

    service._graph.execute.assert_not_called()


@pytest.mark.asyncio
async def test_scan_tick_calls_scan_and_polls_contradictions(
    service: ProactiveService,
) -> None:
    mock_detector = MagicMock()
    mock_detector.list_unresolved = AsyncMock(return_value=[])
    service._contradiction_detector = mock_detector

    with patch.object(service, "_scan_upcoming_meetings", new_callable=AsyncMock) as mock_scan:
        await service._scan_tick()
        mock_scan.assert_called_once()

    mock_detector.list_unresolved.assert_called_once()


@pytest.mark.asyncio
async def test_scan_tick_no_contradiction_detector(
    service: ProactiveService,
) -> None:
    """_scan_tick must not raise if no contradiction detector is wired."""
    service._contradiction_detector = None

    with patch.object(service, "_scan_upcoming_meetings", new_callable=AsyncMock):
        await service._scan_tick()  # should not raise


# ---------------------------------------------------------------------------
# Webhook delivery — extensibility API (NXP-88 / FR-6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_not_delivered_when_no_url_configured(
    service: ProactiveService,
) -> None:
    """No HTTP call is made when neither global nor type-specific URL is set."""
    notif = _make_notification("n-1", NotificationType.INSIGHT)
    prefs = NotificationPreferences()  # all webhook URLs are None

    with patch("nexuspkm.services.proactive.httpx.AsyncClient") as mock_client_cls:
        await service._deliver_webhook(notif, prefs)
        mock_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_uses_global_url_as_fallback(
    service: ProactiveService,
) -> None:
    """When no type-specific URL is set, the global webhook_url is used."""
    notif = _make_notification("n-1", NotificationType.MEETING_PREP)
    prefs = NotificationPreferences(webhook_url="https://hook.example.com/all")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("nexuspkm.services.proactive.httpx.AsyncClient", return_value=mock_client):
        await service._deliver_webhook(notif, prefs)

    mock_client.post.assert_called_once()
    call_url = mock_client.post.call_args[0][0]
    assert call_url == "https://hook.example.com/all"


@pytest.mark.asyncio
async def test_webhook_uses_type_specific_url_over_global(
    service: ProactiveService,
) -> None:
    """Type-specific webhook URL takes precedence over the global URL."""
    notif = _make_notification("n-1", NotificationType.MEETING_PREP)
    prefs = NotificationPreferences(
        webhook_url="https://hook.example.com/all",
        webhook_url_meeting_prep="https://hook.example.com/meetings",
    )

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock()

    with patch("nexuspkm.services.proactive.httpx.AsyncClient", return_value=mock_client):
        await service._deliver_webhook(notif, prefs)

    call_url = mock_client.post.call_args[0][0]
    assert call_url == "https://hook.example.com/meetings"


@pytest.mark.asyncio
async def test_webhook_type_specific_url_for_each_type(
    service: ProactiveService,
) -> None:
    """Each notification type routes to its own webhook URL when configured."""
    prefs = NotificationPreferences(
        webhook_url_meeting_prep="https://hook.example.com/meetings",
        webhook_url_related_content="https://hook.example.com/related",
        webhook_url_contradiction="https://hook.example.com/contradiction",
        webhook_url_insight="https://hook.example.com/insight",
    )
    type_url_pairs = [
        (NotificationType.MEETING_PREP, "https://hook.example.com/meetings"),
        (NotificationType.RELATED_CONTENT, "https://hook.example.com/related"),
        (NotificationType.CONTRADICTION, "https://hook.example.com/contradiction"),
        (NotificationType.INSIGHT, "https://hook.example.com/insight"),
    ]

    for ntype, expected_url in type_url_pairs:
        notif = _make_notification("n-1", ntype)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock()

        with patch("nexuspkm.services.proactive.httpx.AsyncClient", return_value=mock_client):
            await service._deliver_webhook(notif, prefs)

        call_url = mock_client.post.call_args[0][0]
        assert call_url == expected_url, f"Wrong URL for {ntype}"


@pytest.mark.asyncio
async def test_webhook_rejects_non_https_type_specific_url(
    service: ProactiveService,
) -> None:
    """Non-HTTPS type-specific URLs are rejected (no HTTP call made)."""
    notif = _make_notification("n-1", NotificationType.CONTRADICTION)
    prefs = NotificationPreferences(webhook_url_contradiction="http://insecure.example.com/hook")

    with patch("nexuspkm.services.proactive.httpx.AsyncClient") as mock_client_cls:
        await service._deliver_webhook(notif, prefs)
        mock_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_payload_contains_notification_data(
    service: ProactiveService,
) -> None:
    """Webhook POST body is the full notification serialised as JSON."""
    notif = _make_notification("n-webhook", NotificationType.INSIGHT)
    prefs = NotificationPreferences(webhook_url_insight="https://hook.example.com/insight")

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock()

    with patch("nexuspkm.services.proactive.httpx.AsyncClient", return_value=mock_client):
        await service._deliver_webhook(notif, prefs)

    call_kwargs = mock_client.post.call_args[1]
    payload = call_kwargs["json"]
    assert payload["id"] == "n-webhook"
    assert payload["type"] == "insight"


@pytest.mark.asyncio
async def test_webhook_per_type_preferences_persisted(
    mock_graph: MagicMock,
    mock_llm: MagicMock,
    db_path: Path,
) -> None:
    """Per-type webhook URLs round-trip through save/load correctly."""
    svc = ProactiveService(mock_graph, mock_llm, db_path)
    await svc.init()

    prefs = NotificationPreferences(
        webhook_url="https://global.example.com/hook",
        webhook_url_meeting_prep="https://meeting.example.com/hook",
        webhook_url_related_content="https://related.example.com/hook",
        webhook_url_contradiction="https://contradiction.example.com/hook",
        webhook_url_insight="https://insight.example.com/hook",
    )
    await svc.save_preferences(prefs)
    loaded = await svc.get_preferences()

    assert loaded.webhook_url == "https://global.example.com/hook"
    assert loaded.webhook_url_meeting_prep == "https://meeting.example.com/hook"
    assert loaded.webhook_url_related_content == "https://related.example.com/hook"
    assert loaded.webhook_url_contradiction == "https://contradiction.example.com/hook"
    assert loaded.webhook_url_insight == "https://insight.example.com/hook"


@pytest.mark.asyncio
async def test_webhook_per_type_defaults_to_none(service: ProactiveService) -> None:
    """All per-type webhook URLs default to None."""
    prefs = await service.get_preferences()
    assert prefs.webhook_url_meeting_prep is None
    assert prefs.webhook_url_related_content is None
    assert prefs.webhook_url_contradiction is None
    assert prefs.webhook_url_insight is None
