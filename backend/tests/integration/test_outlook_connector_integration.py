"""Integration tests for Outlook Connector with mocked Microsoft Graph API.

Tests full sync flows including delta queries, thread grouping, calendar sync,
and deleted email handling.

Spec refs: F-010
NXP-69
"""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from nexuspkm.config.models import OutlookConnectorConfig
from nexuspkm.connectors.ms_graph.outlook import OutlookConnector
from nexuspkm.models.document import SourceType, SyncState


def _make_connector(tmp_path: Path, **config_kwargs: object) -> OutlookConnector:
    return OutlookConnector(
        token_dir=tmp_path / "tokens",
        state_dir=tmp_path / "state",
        config=OutlookConnectorConfig(**config_kwargs),
    )


def _email(
    id: str,
    conversation_id: str,
    subject: str = "Test",
    received: str = "2026-03-15T09:00:00Z",
    sender: str = "alice@example.com",
    folder_id: str = "inbox-id",
    removed: bool = False,
) -> dict[str, object]:
    if removed:
        return {
            "id": id,
            "@removed": {"reason": "deleted"},
        }
    return {
        "id": id,
        "conversationId": conversation_id,
        "subject": subject,
        "body": {"content": "<p>Body</p>", "contentType": "html"},
        "sender": {"emailAddress": {"address": sender}},
        "toRecipients": [{"emailAddress": {"address": "bob@example.com"}}],
        "ccRecipients": [],
        "receivedDateTime": received,
        "parentFolderId": folder_id,
        "isRead": True,
    }


def _calendar_event(
    id: str,
    subject: str = "Meeting",
    start: str = "2026-03-15T09:00:00Z",
    end: str = "2026-03-15T10:00:00Z",
    attendees: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": id,
        "subject": subject,
        "start": {"dateTime": start, "timeZone": "UTC"},
        "end": {"dateTime": end, "timeZone": "UTC"},
        "body": {"content": "<p>Details</p>", "contentType": "html"},
        "organizer": {"emailAddress": {"address": "alice@example.com"}},
        "attendees": [
            {"emailAddress": {"address": a}, "type": "required"} for a in (attendees or [])
        ],
        "isOnlineMeeting": False,
        "recurrence": None,
        "webLink": f"https://outlook.office365.com/calendar/event/{id}",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFullEmailSync:
    async def test_initial_email_sync_yields_thread_documents(self, tmp_path: Path) -> None:
        """Initial sync with no delta token fetches all emails and groups into threads."""
        connector = _make_connector(tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        emails = [
            _email("e1", "conv-A", subject="Project Update"),
            _email("e2", "conv-B", subject="Team Meeting"),
            _email("e3", "conv-A", subject="Re: Project Update"),
        ]
        folder_map = {"inbox-id": "Inbox"}

        with (
            patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")),
            patch.object(
                connector,
                "_list_emails_delta",
                new=AsyncMock(return_value=(emails, "delta-token-v1", [])),
            ),
            patch.object(
                connector,
                "_list_calendar_events",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                connector,
                "_get_folder_name",
                new=AsyncMock(side_effect=lambda client, token, fid: folder_map.get(fid, "Inbox")),
            ),
        ):
            docs = [doc async for doc in connector.fetch()]

        # 2 threads (conv-A and conv-B), 0 calendar events
        email_docs = [d for d in docs if d.metadata.source_type == SourceType.OUTLOOK_EMAIL]
        assert len(email_docs) == 2

    async def test_delta_sync_uses_stored_token(self, tmp_path: Path) -> None:
        """On subsequent sync, the stored delta token is passed to _list_emails_delta."""
        connector = _make_connector(tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        stored_state = SyncState(extra={"email_delta_token": "stored-delta-token"})
        await connector.restore_sync_state(stored_state)

        captured_tokens: list[str | None] = []

        async def mock_list_delta(
            _client: object, _token: str, delta_token: str | None
        ) -> tuple[list[dict[str, object]], str | None, list[str]]:
            captured_tokens.append(delta_token)
            return [], "new-delta-token", []

        with (
            patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")),
            patch.object(
                connector, "_list_emails_delta", new=AsyncMock(side_effect=mock_list_delta)
            ),
            patch.object(connector, "_list_calendar_events", new=AsyncMock(return_value=[])),
        ):
            _ = [doc async for doc in connector.fetch()]

        assert captured_tokens == ["stored-delta-token"]

    async def test_delta_token_updated_after_sync(self, tmp_path: Path) -> None:
        """After a sync, the new delta token is persisted to state."""
        connector = _make_connector(tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")),
            patch.object(
                connector,
                "_list_emails_delta",
                new=AsyncMock(return_value=([], "new-delta-token-v2", [])),
            ),
            patch.object(connector, "_list_calendar_events", new=AsyncMock(return_value=[])),
        ):
            _ = [doc async for doc in connector.fetch()]

        state = await connector.get_sync_state()
        assert state.extra.get("email_delta_token") == "new-delta-token-v2"


class TestThreadUpdate:
    async def test_new_email_in_existing_conversation(self, tmp_path: Path) -> None:
        """New email in existing thread updates the thread document."""
        connector = _make_connector(tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        first_email = _email("e1", "conv-A", subject="Hello", received="2026-03-14T09:00:00Z")
        second_email = _email("e2", "conv-A", subject="Re: Hello", received="2026-03-15T09:00:00Z")

        with (
            patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")),
            patch.object(
                connector,
                "_list_emails_delta",
                new=AsyncMock(return_value=([first_email, second_email], "delta-v2", [])),
            ),
            patch.object(connector, "_list_calendar_events", new=AsyncMock(return_value=[])),
            patch.object(
                connector,
                "_get_folder_name",
                new=AsyncMock(return_value="Inbox"),
            ),
        ):
            docs = [doc async for doc in connector.fetch()]

        email_docs = [d for d in docs if d.metadata.source_type == SourceType.OUTLOOK_EMAIL]
        assert len(email_docs) == 1
        # updated_at should be the most recent email's time
        expected_ts = datetime.datetime(2026, 3, 15, 9, 0, 0, tzinfo=datetime.UTC)
        assert email_docs[0].metadata.updated_at == expected_ts


class TestCalendarSync:
    async def test_calendar_sync_yields_documents(self, tmp_path: Path) -> None:
        """Calendar events are fetched and yielded as OUTLOOK_CALENDAR documents."""
        connector = _make_connector(tmp_path, calendar_window_days=30)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        events = [
            _calendar_event("ev1", subject="Sprint Review"),
            _calendar_event("ev2", subject="1:1 with Manager"),
        ]

        with (
            patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")),
            patch.object(
                connector,
                "_list_emails_delta",
                new=AsyncMock(return_value=([], None, [])),
            ),
            patch.object(
                connector,
                "_list_calendar_events",
                new=AsyncMock(return_value=events),
            ),
        ):
            docs = [doc async for doc in connector.fetch()]

        cal_docs = [d for d in docs if d.metadata.source_type == SourceType.OUTLOOK_CALENDAR]
        assert len(cal_docs) == 2

    async def test_calendar_event_with_attendees(self, tmp_path: Path) -> None:
        """Attendees from calendar events are included in document participants."""
        connector = _make_connector(tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        events = [
            _calendar_event(
                "ev1",
                subject="Workshop",
                attendees=["bob@example.com", "charlie@example.com"],
            )
        ]

        with (
            patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")),
            patch.object(
                connector,
                "_list_emails_delta",
                new=AsyncMock(return_value=([], None, [])),
            ),
            patch.object(connector, "_list_calendar_events", new=AsyncMock(return_value=events)),
        ):
            docs = [doc async for doc in connector.fetch()]

        cal_docs = [d for d in docs if d.metadata.source_type == SourceType.OUTLOOK_CALENDAR]
        assert len(cal_docs) == 1
        participants = cal_docs[0].metadata.participants
        assert "bob@example.com" in participants
        assert "charlie@example.com" in participants


class TestDeletedEmailHandling:
    async def test_deleted_emails_tracked_in_state(self, tmp_path: Path) -> None:
        """Emails returned with @removed in delta are tracked as deleted source IDs."""
        connector = _make_connector(tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")),
            patch.object(
                connector,
                "_list_emails_delta",
                new=AsyncMock(return_value=([], "delta-v3", ["conv-X"])),
            ),
            patch.object(connector, "_list_calendar_events", new=AsyncMock(return_value=[])),
        ):
            _ = [doc async for doc in connector.fetch()]

        state = await connector.get_sync_state()
        deleted_ids = state.extra.get("deleted_source_ids", [])
        assert isinstance(deleted_ids, list)
        assert "conv-X" in deleted_ids

    async def test_fetch_deleted_ids_returns_tracked_ids(self, tmp_path: Path) -> None:
        """fetch_deleted_ids returns conversation IDs marked as deleted in state."""
        connector = _make_connector(tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        state = SyncState(extra={"deleted_source_ids": ["conv-deleted-1", "conv-deleted-2"]})
        await connector.restore_sync_state(state)

        deleted = await connector.fetch_deleted_ids()
        assert "conv-deleted-1" in deleted
        assert "conv-deleted-2" in deleted
