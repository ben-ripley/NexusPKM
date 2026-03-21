"""Unit tests for Outlook Connector.

Covers: connectors/ms_graph/outlook.py
Spec refs: F-010
NXP-69
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from nexuspkm.config.models import OutlookConnectorConfig
from nexuspkm.connectors.base import ConnectorStatus
from nexuspkm.connectors.ms_graph.outlook import OutlookConnector, _html_to_text
from nexuspkm.models.document import Document, SourceType, SyncState

_DATE = datetime.datetime(2026, 3, 15, 9, 0, 0, tzinfo=datetime.UTC)
_DUMMY_REQUEST = httpx.Request("GET", "https://graph.microsoft.com/v1.0/test")


def _make_response(
    status_code: int,
    *,
    json_body: dict[str, object] | None = None,
    text_body: str | None = None,
) -> httpx.Response:
    if text_body is not None:
        return httpx.Response(status_code, text=text_body, request=_DUMMY_REQUEST)
    return httpx.Response(status_code, json=json_body or {}, request=_DUMMY_REQUEST)


def _make_connector(tmp_path: Path, **config_kwargs: object) -> OutlookConnector:
    return OutlookConnector(
        token_dir=tmp_path / "tokens",
        state_dir=tmp_path / "state",
        config=OutlookConnectorConfig(**config_kwargs),
    )


def _make_email(
    *,
    id: str = "email-001",
    conversation_id: str = "conv-001",
    subject: str = "Test Email",
    body_html: str = "<p>Hello</p>",
    sender_email: str = "alice@example.com",
    received_datetime: str = "2026-03-15T09:00:00Z",
    parent_folder_name: str = "Inbox",
    is_read: bool = True,
    to_recipients: list[str] | None = None,
    cc_recipients: list[str] | None = None,
) -> dict[str, object]:
    to_recs = to_recipients or ["bob@example.com"]
    return {
        "id": id,
        "conversationId": conversation_id,
        "subject": subject,
        "body": {"content": body_html, "contentType": "html"},
        "sender": {"emailAddress": {"address": sender_email, "name": "Alice"}},
        "toRecipients": [{"emailAddress": {"address": a}} for a in to_recs],
        "ccRecipients": [{"emailAddress": {"address": a}} for a in (cc_recipients or [])],
        "receivedDateTime": received_datetime,
        "parentFolderId": "inbox-id",
        "isRead": is_read,
    }


def _make_calendar_event(
    *,
    id: str = "event-001",
    subject: str = "Team Meeting",
    start: str = "2026-03-15T09:00:00Z",
    end: str = "2026-03-15T10:00:00Z",
    body_html: str = "<p>Agenda</p>",
    organizer_email: str = "alice@example.com",
    attendees: list[str] | None = None,
    is_online_meeting: bool = False,
    is_recurring: bool = False,
) -> dict[str, object]:
    event: dict[str, object] = {
        "id": id,
        "subject": subject,
        "start": {"dateTime": start, "timeZone": "UTC"},
        "end": {"dateTime": end, "timeZone": "UTC"},
        "body": {"content": body_html, "contentType": "html"},
        "organizer": {"emailAddress": {"address": organizer_email, "name": "Alice"}},
        "attendees": [
            {"emailAddress": {"address": a}, "type": "required"} for a in (attendees or [])
        ],
        "isOnlineMeeting": is_online_meeting,
        "recurrence": {"pattern": {"type": "weekly"}} if is_recurring else None,
        "webLink": "https://outlook.office365.com/calendar/event/event-001",
    }
    return event


# ---------------------------------------------------------------------------
# TestHtmlToText
# ---------------------------------------------------------------------------


class TestHtmlToText:
    def test_plain_text_passthrough(self) -> None:
        result = _html_to_text("Hello world")
        assert "Hello world" in result

    def test_html_body_extraction(self) -> None:
        html = "<html><body><p>Hello <b>world</b></p></body></html>"
        result = _html_to_text(html)
        assert "Hello" in result
        assert "world" in result

    def test_empty_body_fallback(self) -> None:
        result = _html_to_text("")
        assert result == ""

    def test_strips_html_tags(self) -> None:
        html = "<p>Some <em>text</em> here</p>"
        result = _html_to_text(html)
        assert "<p>" not in result
        assert "<em>" not in result
        assert "text" in result


# ---------------------------------------------------------------------------
# TestEmailFilters
# ---------------------------------------------------------------------------


class TestEmailFilters:
    def test_folder_filter_allows_inbox(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, folders=["Inbox"])
        email = _make_email(parent_folder_name="Inbox")
        assert connector._apply_email_filters(email, folder_name="Inbox") is True

    def test_folder_filter_blocks_sent_items(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, folders=["Inbox"])
        assert connector._apply_email_filters({}, folder_name="Sent Items") is False

    def test_exclude_folder_blocks_junk(self, tmp_path: Path) -> None:
        connector = _make_connector(
            tmp_path, folders=["Inbox", "Junk Email"], exclude_folders=["Junk Email"]
        )
        assert connector._apply_email_filters({}, folder_name="Junk Email") is False

    def test_sender_domain_filter_allows_matching(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, sender_domains=["example.com"])
        email = _make_email(sender_email="alice@example.com")
        assert connector._apply_email_filters(email, folder_name="Inbox") is True

    def test_sender_domain_filter_blocks_non_matching(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, sender_domains=["example.com"])
        email = _make_email(sender_email="spammer@evil.com")
        assert connector._apply_email_filters(email, folder_name="Inbox") is False

    def test_sender_domain_empty_allows_all(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, sender_domains=[])
        email = _make_email(sender_email="anyone@random.org")
        assert connector._apply_email_filters(email, folder_name="Inbox") is True

    def test_date_from_filter_blocks_old_emails(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, date_from="2026-03-14")
        old_email = _make_email(received_datetime="2026-03-13T09:00:00Z")
        assert connector._apply_email_filters(old_email, folder_name="Inbox") is False

    def test_date_from_filter_allows_recent_emails(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, date_from="2026-03-14")
        recent = _make_email(received_datetime="2026-03-15T09:00:00Z")
        assert connector._apply_email_filters(recent, folder_name="Inbox") is True

    def test_date_from_none_allows_all(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, date_from=None)
        old_email = _make_email(received_datetime="2020-01-01T00:00:00Z")
        assert connector._apply_email_filters(old_email, folder_name="Inbox") is True


# ---------------------------------------------------------------------------
# TestThreadGrouping
# ---------------------------------------------------------------------------


class TestThreadGrouping:
    def test_group_by_conversation_id(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        emails = [
            _make_email(id="e1", conversation_id="conv-A", subject="Thread A"),
            _make_email(id="e2", conversation_id="conv-B", subject="Thread B"),
            _make_email(id="e3", conversation_id="conv-A", subject="Re: Thread A"),
        ]
        docs = connector._build_thread_documents(emails)
        assert len(docs) == 2
        subjects = {d.metadata.title for d in docs}
        # Both conversation IDs produce a doc
        assert len(subjects) == 2

    def test_single_email_thread(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        emails = [_make_email(id="e1", conversation_id="conv-A")]
        docs = connector._build_thread_documents(emails)
        assert len(docs) == 1

    def test_participants_union_across_thread(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        emails = [
            _make_email(
                id="e1",
                conversation_id="conv-X",
                sender_email="alice@example.com",
                to_recipients=["bob@example.com"],
            ),
            _make_email(
                id="e2",
                conversation_id="conv-X",
                sender_email="bob@example.com",
                to_recipients=["alice@example.com"],
                cc_recipients=["charlie@example.com"],
            ),
        ]
        docs = connector._build_thread_documents(emails)
        assert len(docs) == 1
        participants = set(docs[0].metadata.participants)
        assert "alice@example.com" in participants
        assert "bob@example.com" in participants
        assert "charlie@example.com" in participants

    def test_empty_email_list(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        docs = connector._build_thread_documents([])
        assert docs == []


# ---------------------------------------------------------------------------
# TestEmailThreadDocument
# ---------------------------------------------------------------------------


class TestEmailThreadDocument:
    def test_thread_document_transformation(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        emails = [_make_email(conversation_id="conv-001")]
        doc = connector._to_email_thread_document(emails)

        assert isinstance(doc, Document)
        assert doc.metadata.source_type == SourceType.OUTLOOK_EMAIL
        assert doc.metadata.source_id == "conv-001"
        assert len(doc.content) > 0

    def test_deterministic_id(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        emails = [_make_email(conversation_id="conv-001")]
        doc1 = connector._to_email_thread_document(emails)
        doc2 = connector._to_email_thread_document(emails)
        assert doc1.id == doc2.id

    def test_id_differs_by_conversation(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        emails_a = [_make_email(conversation_id="conv-A")]
        emails_b = [_make_email(conversation_id="conv-B")]
        doc_a = connector._to_email_thread_document(emails_a)
        doc_b = connector._to_email_thread_document(emails_b)
        assert doc_a.id != doc_b.id

    def test_most_recent_email_sets_timestamp(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        emails = [
            _make_email(
                id="e1",
                conversation_id="conv-001",
                received_datetime="2026-03-14T09:00:00Z",
            ),
            _make_email(
                id="e2",
                conversation_id="conv-001",
                received_datetime="2026-03-15T09:00:00Z",
            ),
        ]
        doc = connector._to_email_thread_document(emails)
        expected = datetime.datetime(2026, 3, 15, 9, 0, 0, tzinfo=datetime.UTC)
        assert doc.metadata.updated_at == expected


# ---------------------------------------------------------------------------
# TestCalendarDocument
# ---------------------------------------------------------------------------


class TestCalendarDocument:
    def test_event_to_document(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        event = _make_calendar_event()
        doc = connector._to_calendar_document(event)

        assert isinstance(doc, Document)
        assert doc.metadata.source_type == SourceType.OUTLOOK_CALENDAR
        assert doc.metadata.source_id == "event-001"
        assert "Team Meeting" in doc.metadata.title
        assert len(doc.content) > 0

    def test_online_meeting_flag_in_custom(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        event = _make_calendar_event(is_online_meeting=True)
        doc = connector._to_calendar_document(event)
        assert doc.metadata.custom.get("is_online_meeting") is True

    def test_recurring_event_flag_in_custom(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        event = _make_calendar_event(is_recurring=True)
        doc = connector._to_calendar_document(event)
        assert doc.metadata.custom.get("is_recurring") is True

    def test_attendees_in_participants(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        event = _make_calendar_event(attendees=["bob@example.com", "charlie@example.com"])
        doc = connector._to_calendar_document(event)
        assert "bob@example.com" in doc.metadata.participants
        assert "charlie@example.com" in doc.metadata.participants

    def test_deterministic_id(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        event = _make_calendar_event(id="event-001")
        doc1 = connector._to_calendar_document(event)
        doc2 = connector._to_calendar_document(event)
        assert doc1.id == doc2.id

    def test_empty_body_fallback(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        event = _make_calendar_event(body_html="")
        doc = connector._to_calendar_document(event)
        assert len(doc.content) > 0  # Should use subject as fallback


# ---------------------------------------------------------------------------
# TestRateLimitRetry
# ---------------------------------------------------------------------------


class TestRateLimitRetry:
    async def test_rate_limit_retry_on_429(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.request = AsyncMock(
            side_effect=[
                _make_response(429),
                _make_response(200, json_body={"value": []}),
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            response = await connector._request_with_retry(
                mock_client, "GET", "https://example.com"
            )

        assert response.status_code == 200
        assert mock_client.request.call_count == 2

    async def test_rate_limit_max_retries_raises(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.request = AsyncMock(side_effect=[_make_response(429)] * 4)

        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await connector._request_with_retry(mock_client, "GET", "https://example.com")

        assert mock_client.request.call_count == 4

    async def test_first_attempt_succeeds(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.request = AsyncMock(return_value=_make_response(200, json_body={}))

        response = await connector._request_with_retry(mock_client, "GET", "https://example.com")

        assert response.status_code == 200
        assert mock_client.request.call_count == 1


# ---------------------------------------------------------------------------
# TestSyncState
# ---------------------------------------------------------------------------


class TestSyncState:
    async def test_get_sync_state_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        state = await connector.get_sync_state()

        assert isinstance(state, SyncState)
        assert state.last_synced_at is None
        assert state.cursor is None

    async def test_restore_sync_state_writes_file(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        since = datetime.datetime(2026, 3, 19, 12, 0, 0, tzinfo=datetime.UTC)
        new_state = SyncState(last_synced_at=since)
        await connector.restore_sync_state(new_state)

        state_file = state_dir / "outlook_sync_state.json"
        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert "last_synced_at" in data

    async def test_delta_token_persisted_in_extra(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        state = SyncState(extra={"email_delta_token": "delta-token-abc"})
        await connector.restore_sync_state(state)

        loaded = await connector.get_sync_state()
        assert loaded.extra.get("email_delta_token") == "delta-token-abc"

    async def test_get_sync_state_loads_from_file(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        since = datetime.datetime(2026, 3, 10, 12, 0, 0, tzinfo=datetime.UTC)
        state_data = {
            "last_synced_at": since.isoformat(),
            "cursor": None,
            "documents_synced": 0,
            "extra": {"email_delta_token": "delta-xyz"},
        }
        (state_dir / "outlook_sync_state.json").write_text(json.dumps(state_data))

        state = await connector.get_sync_state()
        assert state.last_synced_at == since
        assert state.extra.get("email_delta_token") == "delta-xyz"


# ---------------------------------------------------------------------------
# TestAuthenticate
# ---------------------------------------------------------------------------


class TestAuthenticate:
    async def test_authenticate_returns_true_when_token_available(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        with patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")):
            result = await connector.authenticate()
        assert result is True

    async def test_authenticate_returns_false_when_no_token(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        with patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value=None)):
            result = await connector.authenticate()
        assert result is False


# ---------------------------------------------------------------------------
# TestHealthCheck
# ---------------------------------------------------------------------------


class TestHealthCheck:
    async def test_health_check_healthy_when_token_available(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        with patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")):
            status = await connector.health_check()

        assert isinstance(status, ConnectorStatus)
        assert status.status == "healthy"
        assert status.name == "outlook"

    async def test_health_check_degraded_when_no_token(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        with patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value=None)):
            status = await connector.health_check()

        assert status.status == "degraded"


# ---------------------------------------------------------------------------
# TestFetch
# ---------------------------------------------------------------------------


class TestFetch:
    async def test_fetch_yields_email_and_calendar_docs(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        email_doc = MagicMock(spec=Document)
        calendar_doc = MagicMock(spec=Document)

        with (
            patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")),
            patch.object(
                connector,
                "_fetch_emails",
                new=AsyncMock(return_value=([email_doc], "new-delta-token", [])),
            ),
            patch.object(
                connector,
                "_fetch_calendar",
                new=AsyncMock(return_value=[calendar_doc]),
            ),
        ):
            docs = [doc async for doc in connector.fetch()]

        assert email_doc in docs
        assert calendar_doc in docs
        assert len(docs) == 2

    async def test_fetch_returns_empty_when_no_token(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        with patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value=None)):
            docs = [doc async for doc in connector.fetch()]
        assert docs == []

    async def test_fetch_updates_delta_token_in_state(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")),
            patch.object(
                connector,
                "_fetch_emails",
                new=AsyncMock(return_value=([], "updated-delta-token", [])),
            ),
            patch.object(connector, "_fetch_calendar", new=AsyncMock(return_value=[])),
        ):
            _ = [doc async for doc in connector.fetch()]

        state = await connector.get_sync_state()
        assert state.extra.get("email_delta_token") == "updated-delta-token"

    async def test_fetch_skips_filtered_emails(self, tmp_path: Path) -> None:
        """Connector with strict domain filter yields no emails from wrong domain."""
        connector = _make_connector(tmp_path, sender_domains=["allowed.com"])

        raw_emails = [_make_email(sender_email="bob@blocked.com")]

        with (
            patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")),
            patch.object(
                connector,
                "_list_emails_delta",
                new=AsyncMock(return_value=(raw_emails, None, [])),
            ),
            patch.object(connector, "_fetch_calendar", new=AsyncMock(return_value=[])),
            patch.object(
                connector,
                "_get_folder_name",
                new=AsyncMock(return_value="Inbox"),
            ),
        ):
            docs = [doc async for doc in connector.fetch()]

        assert docs == []


# ---------------------------------------------------------------------------
# TestFetchDeletedIds
# ---------------------------------------------------------------------------


class TestFetchDeletedIds:
    async def test_returns_deleted_ids_from_state(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        deleted_id = "some-doc-uuid"
        state = SyncState(extra={"deleted_source_ids": [deleted_id]})
        await connector.restore_sync_state(state)

        ids = await connector.fetch_deleted_ids()
        assert deleted_id in ids

    async def test_returns_empty_when_no_deletions(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        ids = await connector.fetch_deleted_ids()
        assert ids == []
