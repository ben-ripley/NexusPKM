"""Unit tests for Teams Transcript Connector.

Covers: connectors/ms_graph/teams.py
Spec refs: F-003 FR-2, FR-5, FR-6, FR-7
NXP-54, NXP-56
"""

from __future__ import annotations

import datetime
import json
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from nexuspkm.config.models import TeamsConnectorConfig
from nexuspkm.connectors.base import ConnectorStatus
from nexuspkm.connectors.ms_graph.teams import TeamsTranscriptConnector
from nexuspkm.connectors.ms_graph.vtt_parser import ParsedTranscript, TranscriptSegment
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


def _make_connector(tmp_path: Path) -> TeamsTranscriptConnector:
    return TeamsTranscriptConnector(
        token_dir=tmp_path / "tokens",
        state_dir=tmp_path / "state",
        config=TeamsConnectorConfig(),
    )


def _make_parsed_transcript() -> ParsedTranscript:
    return ParsedTranscript(
        meeting_id="meeting-001",
        title="Team Standup",
        date=_DATE,
        duration_minutes=30,
        participants=["Alice Smith", "Bob Jones"],
        segments=[
            TranscriptSegment(
                speaker="Alice Smith",
                start_time="00:00:01.000",
                end_time="00:00:05.000",
                text="Hello everyone.",
            ),
            TranscriptSegment(
                speaker="Bob Jones",
                start_time="00:00:05.500",
                end_time="00:00:10.000",
                text="Thanks Alice.",
            ),
        ],
        full_text="Alice Smith: Hello everyone.\nBob Jones: Thanks Alice.\n",
    )


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


class TestToDocument:
    def test_to_document_transforms_parsed_transcript(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        parsed = _make_parsed_transcript()
        doc = connector._to_document(parsed)

        assert isinstance(doc, Document)
        assert doc.metadata.source_type == SourceType.TEAMS_TRANSCRIPT
        assert doc.metadata.source_id == "meeting-001"
        assert doc.metadata.title == "Meeting: Team Standup"
        assert doc.metadata.participants == ["Alice Smith", "Bob Jones"]
        assert doc.metadata.created_at == _DATE
        assert doc.metadata.updated_at == _DATE
        assert doc.content == "Alice Smith: Hello everyone.\nBob Jones: Thanks Alice.\n"
        assert doc.metadata.custom["duration_minutes"] == 30
        segments = doc.metadata.custom["segments"]
        assert isinstance(segments, list)
        assert len(segments) == 2

    def test_to_document_empty_content_fallback(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        parsed = ParsedTranscript(
            meeting_id="m-001",
            title="Empty Meeting",
            date=_DATE,
            duration_minutes=0,
            participants=[],
            segments=[],
            full_text="",
        )
        doc = connector._to_document(parsed)
        assert len(doc.content) > 0

    def test_to_document_id_is_deterministic(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        parsed = _make_parsed_transcript()
        doc1 = connector._to_document(parsed)
        doc2 = connector._to_document(parsed)
        assert doc1.id == doc2.id


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
        mock_client.request = AsyncMock(
            side_effect=[_make_response(429)] * 4  # 4 consecutive 429s
        )

        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await connector._request_with_retry(mock_client, "GET", "https://example.com")

        assert mock_client.request.call_count == 4

    async def test_rate_limit_first_attempt_succeeds(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.request = AsyncMock(return_value=_make_response(200, json_body={}))

        response = await connector._request_with_retry(mock_client, "GET", "https://example.com")

        assert response.status_code == 200
        assert mock_client.request.call_count == 1


class TestSyncState:
    async def test_get_sync_state_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        state = await connector.get_sync_state()

        assert isinstance(state, SyncState)
        assert state.last_synced_at is None
        assert state.cursor is None

    async def test_get_sync_state_loads_from_file(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        since = datetime.datetime(2026, 3, 10, 12, 0, 0, tzinfo=datetime.UTC)
        state_data = {"last_synced_at": since.isoformat(), "cursor": None, "extra": {}}
        (state_dir / "teams_sync_state.json").write_text(json.dumps(state_data))

        state = await connector.get_sync_state()

        assert state.last_synced_at == since

    async def test_restore_sync_state_writes_file(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        since = datetime.datetime(2026, 3, 19, 12, 0, 0, tzinfo=datetime.UTC)
        new_state = SyncState(last_synced_at=since)
        await connector.restore_sync_state(new_state)

        state_file = state_dir / "teams_sync_state.json"
        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert "last_synced_at" in data


class TestFetch:
    async def test_fetch_yields_documents(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        sample_vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\n<v Alice>Hello everyone.</v>\n"

        with (
            patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")),
            patch.object(
                connector,
                "_list_meetings",
                return_value=_async_gen(
                    [
                        {
                            "id": "meeting-001",
                            "subject": "Standup",
                            "startDateTime": "2026-03-15T09:00:00Z",
                            "endDateTime": "2026-03-15T09:30:00Z",
                            "attendees": [],
                        }
                    ]
                ),
            ),
            patch.object(
                connector,
                "_list_transcripts",
                new=AsyncMock(return_value=[{"id": "transcript-001"}]),
            ),
            patch.object(connector, "_fetch_vtt", new=AsyncMock(return_value=sample_vtt)),
        ):
            docs = [doc async for doc in connector.fetch()]

        assert len(docs) == 1
        assert isinstance(docs[0], Document)
        assert docs[0].metadata.source_id == "meeting-001"

    async def test_fetch_skips_meetings_without_transcripts(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)

        with (
            patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")),
            patch.object(
                connector,
                "_list_meetings",
                return_value=_async_gen(
                    [
                        {
                            "id": "meeting-no-transcripts",
                            "subject": "No Transcript",
                            "startDateTime": "2026-03-15T09:00:00Z",
                            "endDateTime": "2026-03-15T09:30:00Z",
                            "attendees": [],
                        }
                    ]
                ),
            ),
            patch.object(connector, "_list_transcripts", new=AsyncMock(return_value=[])),
        ):
            docs = [doc async for doc in connector.fetch()]

        assert docs == []

    async def test_fetch_handles_malformed_vtt_gracefully(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        bad_vtt = "WEBVTT\n\nNOT A VALID CUE\n"

        with (
            patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")),
            patch.object(
                connector,
                "_list_meetings",
                return_value=_async_gen(
                    [
                        {
                            "id": "meeting-001",
                            "subject": "Standup",
                            "startDateTime": "2026-03-15T09:00:00Z",
                            "endDateTime": "2026-03-15T09:30:00Z",
                            "attendees": [],
                        }
                    ]
                ),
            ),
            patch.object(
                connector, "_list_transcripts", new=AsyncMock(return_value=[{"id": "t-001"}])
            ),
            patch.object(connector, "_fetch_vtt", new=AsyncMock(return_value=bad_vtt)),
        ):
            docs = [doc async for doc in connector.fetch()]

        assert len(docs) == 1
        assert isinstance(docs[0], Document)

    async def test_fetch_returns_empty_when_no_token(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        with patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value=None)):
            docs = [doc async for doc in connector.fetch()]
        assert docs == []


class TestHealthCheck:
    async def test_health_check_healthy_when_token_available(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        with patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")):
            status = await connector.health_check()

        assert isinstance(status, ConnectorStatus)
        assert status.status == "healthy"
        assert status.name == "teams"

    async def test_health_check_degraded_when_no_token(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        with patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value=None)):
            status = await connector.health_check()

        assert status.status == "degraded"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _async_gen(items: list[dict[str, object]]) -> AsyncGenerator[dict[str, object], None]:
    for item in items:
        yield item
