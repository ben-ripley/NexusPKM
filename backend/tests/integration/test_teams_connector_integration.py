"""Integration tests for Teams Transcript Connector with mocked Graph API.

Uses httpx mock transport to simulate Graph API responses end-to-end.

Spec refs: F-003 FR-2, FR-3, FR-6
NXP-54, NXP-56
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from nexuspkm.config.models import TeamsConnectorConfig
from nexuspkm.connectors.ms_graph.teams import TeamsTranscriptConnector
from nexuspkm.models.document import Document, SourceType

_SAMPLE_VTT = """\
WEBVTT

00:00:01.000 --> 00:00:05.000
<v Alice Smith>Hello everyone, let's get started.</v>

00:00:05.500 --> 00:00:10.000
<v Bob Jones>Thanks Alice. Ready to go.</v>
"""

_MEETINGS_RESPONSE = {
    "value": [
        {
            "id": "meeting-001",
            "subject": "Team Standup",
            "startDateTime": "2026-03-15T09:00:00Z",
            "endDateTime": "2026-03-15T09:30:00Z",
            "attendees": [
                {"identity": {"user": {"displayName": "Alice Smith"}}},
                {"identity": {"user": {"displayName": "Bob Jones"}}},
            ],
        }
    ]
}

_TRANSCRIPTS_RESPONSE = {"value": [{"id": "transcript-001"}]}

_DUMMY_REQUEST = httpx.Request("GET", "https://graph.microsoft.com/v1.0/test")


def _make_connector(tmp_path: Path) -> TeamsTranscriptConnector:
    return TeamsTranscriptConnector(
        token_dir=tmp_path / "tokens",
        state_dir=tmp_path / "state",
        config=TeamsConnectorConfig(),
    )


class TestFullSyncFlow:
    async def test_full_sync_flow_mocked_graph_api(self, tmp_path: Path) -> None:
        """Full fetch() flow: meetings → transcripts → VTT → Documents."""
        connector = _make_connector(tmp_path)

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/transcripts/transcript-001/content" in url:
                return httpx.Response(200, text=_SAMPLE_VTT, request=request)
            if "/transcripts" in url:
                return httpx.Response(200, json=_TRANSCRIPTS_RESPONSE, request=request)
            if "/onlineMeetings" in url:
                return httpx.Response(200, json=_MEETINGS_RESPONSE, request=request)
            return httpx.Response(404, request=request)

        with (
            patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")),
            patch("nexuspkm.connectors.ms_graph.teams.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.request = AsyncMock(side_effect=_route_request(handler))

            docs = [doc async for doc in connector.fetch()]

        assert len(docs) == 1
        doc = docs[0]
        assert isinstance(doc, Document)
        assert doc.metadata.source_type == SourceType.TEAMS_TRANSCRIPT
        assert doc.metadata.source_id == "meeting-001"
        assert doc.metadata.title == "Meeting: Team Standup"
        assert "Alice Smith" in doc.metadata.participants
        assert "Bob Jones" in doc.metadata.participants
        assert "Alice Smith:" in doc.content

    async def test_pagination_handling(self, tmp_path: Path) -> None:
        """@odata.nextLink pagination yields documents from all pages."""
        connector = _make_connector(tmp_path)

        page1 = {
            "value": [
                {
                    "id": "meeting-001",
                    "subject": "Meeting 1",
                    "startDateTime": "2026-03-15T09:00:00Z",
                    "endDateTime": "2026-03-15T09:30:00Z",
                    "attendees": [],
                }
            ],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/onlineMeetings?$skiptoken=abc",
        }
        page2 = {
            "value": [
                {
                    "id": "meeting-002",
                    "subject": "Meeting 2",
                    "startDateTime": "2026-03-14T09:00:00Z",
                    "endDateTime": "2026-03-14T09:30:00Z",
                    "attendees": [],
                }
            ]
        }

        async def mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            url_str = str(url)
            if "content" in url_str:
                return httpx.Response(200, text=_SAMPLE_VTT, request=_DUMMY_REQUEST)
            if "transcripts" in url_str and "content" not in url_str:
                return httpx.Response(200, json=_TRANSCRIPTS_RESPONSE, request=_DUMMY_REQUEST)
            if "$skiptoken=abc" in url_str:
                return httpx.Response(200, json=page2, request=_DUMMY_REQUEST)
            return httpx.Response(200, json=page1, request=_DUMMY_REQUEST)

        with (
            patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")),
            patch("nexuspkm.connectors.ms_graph.teams.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.request = AsyncMock(side_effect=mock_request)

            docs = [doc async for doc in connector.fetch()]

        assert len(docs) == 2
        source_ids = {d.metadata.source_id for d in docs}
        assert "meeting-001" in source_ids
        assert "meeting-002" in source_ids

    async def test_incremental_sync_uses_since_timestamp(self, tmp_path: Path) -> None:
        """fetch(since=...) sets the $filter query param with the since timestamp."""
        connector = _make_connector(tmp_path)
        since = datetime.datetime(2026, 3, 10, 12, 0, 0, tzinfo=datetime.UTC)

        captured_params: dict[str, object] = {}

        async def mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            if "onlineMeetings" in str(url) and not captured_params:
                params = kwargs.get("params", {})
                captured_params.update(params if isinstance(params, dict) else {})
            return httpx.Response(200, json={"value": []}, request=_DUMMY_REQUEST)

        with (
            patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")),
            patch("nexuspkm.connectors.ms_graph.teams.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.request = AsyncMock(side_effect=mock_request)

            docs = [doc async for doc in connector.fetch(since=since)]

        assert docs == []
        assert "$filter" in captured_params
        filter_val = str(captured_params["$filter"])
        assert "2026-03-10T12:00:00Z" in filter_val

    async def test_fetch_no_token_yields_nothing(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        with patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value=None)):
            docs = [doc async for doc in connector.fetch()]
        assert docs == []

    async def test_fetch_empty_transcript_list_skips_meeting(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)

        async def mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            if "transcripts" in str(url):
                return httpx.Response(200, json={"value": []}, request=_DUMMY_REQUEST)
            return httpx.Response(200, json=_MEETINGS_RESPONSE, request=_DUMMY_REQUEST)

        with (
            patch.object(connector._auth, "get_access_token", new=AsyncMock(return_value="tok")),
            patch("nexuspkm.connectors.ms_graph.teams.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = mock_client_cls.return_value.__aenter__.return_value
            mock_client.request = AsyncMock(side_effect=mock_request)

            docs = [doc async for doc in connector.fetch()]

        assert docs == []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _route_request(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.Response]:
    async def _dispatch(method: str, url: str, **kwargs: object) -> httpx.Response:
        req = httpx.Request(method, url)
        return handler(req)

    return _dispatch
