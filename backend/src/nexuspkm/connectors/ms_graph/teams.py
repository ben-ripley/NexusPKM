"""Teams Transcript Connector — fetches meeting transcripts via Microsoft Graph API.

Authenticates via Device Code Flow (delegated), discovers meetings with
transcripts, downloads VTT content, parses it, and yields Document objects
for ingestion into the knowledge engine.

Spec: F-003
NXP-48, NXP-54, NXP-56
"""

from __future__ import annotations

import asyncio
import datetime
import json
import random
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path
from typing import TypedDict

import httpx
import structlog

from nexuspkm.config.models import TeamsConnectorConfig
from nexuspkm.connectors.base import BaseConnector, ConnectorStatus
from nexuspkm.connectors.ms_graph.auth import AuthFlowContext, DeviceCodeInfo, MicrosoftGraphAuth
from nexuspkm.connectors.ms_graph.vtt_parser import ParsedTranscript, parse_vtt
from nexuspkm.models.document import Document, DocumentMetadata, SourceType, SyncState

log = structlog.get_logger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class TeamsTranscriptConnector(BaseConnector):
    """Ingests Microsoft Teams meeting transcripts via the Graph API."""

    name = "teams"

    def __init__(
        self,
        token_dir: Path,
        state_dir: Path,
        config: TeamsConnectorConfig,
    ) -> None:
        self._auth = MicrosoftGraphAuth(token_dir)
        self._state_file = state_dir / "teams_sync_state.json"
        self._config = config
        self._total_docs_synced = 0

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    async def authenticate(self) -> bool:
        """Return True if a valid access token is available."""
        token = await self._auth.get_access_token()
        return token is not None

    async def initiate_auth_flow(self) -> tuple[DeviceCodeInfo, AuthFlowContext]:
        """Start the Microsoft Graph Device Code auth flow.

        Returns a ``(DeviceCodeInfo, AuthFlowContext)`` tuple.  Display
        ``DeviceCodeInfo.user_code`` and ``verification_uri`` to the user, then
        pass the ``AuthFlowContext`` to ``complete_auth_flow``.
        """
        return await self._auth.initiate_device_code_flow()

    async def complete_auth_flow(self, context: AuthFlowContext) -> bool:
        """Poll for the token after the user completes device code authentication.

        Returns True on success, False if authentication failed or expired.
        """
        return await self._auth.poll_for_token(context)

    def fetch(self, since: datetime.datetime | None = None) -> AsyncIterator[Document]:
        """Return an async iterator of Documents for all meetings since *since*."""
        return self._fetch_gen(since)

    async def health_check(self) -> ConnectorStatus:
        token = await self._auth.get_access_token()
        if token is None:
            return ConnectorStatus(
                name=self.name,
                status="degraded",
                last_error="No valid access token — re-authentication required",
                documents_synced=self._total_docs_synced,
            )
        return ConnectorStatus(
            name=self.name,
            status="healthy",
            documents_synced=self._total_docs_synced,
        )

    async def get_sync_state(self) -> SyncState:
        """Load sync state from disk; return an empty state if the file is missing."""
        state_file = self._state_file

        def _read() -> SyncState:
            if not state_file.exists():
                return SyncState()
            try:
                data = json.loads(state_file.read_text())
                return SyncState.model_validate(data)
            except (json.JSONDecodeError, ValueError):
                log.warning("teams_connector.state_load_failed", path=str(state_file))
                return SyncState()

        return await asyncio.to_thread(_read)

    async def restore_sync_state(self, state: SyncState) -> None:
        """Persist sync state to disk."""
        state_file = self._state_file
        serialized = state.model_dump_json()

        def _write() -> None:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(serialized)

        await asyncio.to_thread(_write)

    # ------------------------------------------------------------------
    # Private: fetch pipeline
    # ------------------------------------------------------------------

    async def _fetch_gen(self, since: datetime.datetime | None) -> AsyncGenerator[Document, None]:
        access_token = await self._auth.get_access_token()
        if access_token is None:
            log.warning("teams_connector.no_token_skipping_fetch")
            return

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            async for meeting in self._list_meetings(client, access_token, since):
                meeting_id = str(meeting.get("id", ""))
                if not meeting_id:
                    continue

                transcripts = await self._list_transcripts(client, access_token, meeting_id)
                if not transcripts:
                    continue

                meeting_meta = _parse_meeting_meta(meeting)

                for transcript in transcripts:
                    transcript_id = str(transcript.get("id", ""))
                    if not transcript_id:
                        continue

                    try:
                        vtt_content = await self._fetch_vtt(
                            client, access_token, meeting_id, transcript_id
                        )
                        parsed = parse_vtt(
                            vtt_content,
                            meeting_id=meeting_id,
                            title=meeting_meta["title"],
                            date=meeting_meta["start_dt"],
                            duration_minutes=meeting_meta["duration_minutes"],
                            participants=meeting_meta["participants"],
                        )
                        doc = self._to_document(parsed, join_web_url=meeting_meta["join_web_url"])
                        self._total_docs_synced += 1
                        yield doc
                    except Exception:
                        log.warning(
                            "teams_connector.transcript_fetch_failed",
                            meeting_id=meeting_id,
                            transcript_id=transcript_id,
                            exc_info=True,
                        )

    # ------------------------------------------------------------------
    # Private: Graph API helpers
    # ------------------------------------------------------------------

    async def _list_meetings(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        since: datetime.datetime | None,
    ) -> AsyncGenerator[dict[str, object], None]:
        headers = {"Authorization": f"Bearer {access_token}"}
        params: dict[str, str] = {"$orderby": "startDateTime desc", "$top": "50"}
        if since is not None:
            since_utc = since.astimezone(datetime.UTC)
            params["$filter"] = f"startDateTime ge {since_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}"

        next_url: str | None = f"{_GRAPH_BASE}/me/onlineMeetings"
        current_params: dict[str, str] | None = params

        while next_url is not None:
            response = await self._request_with_retry(
                client,
                "GET",
                next_url,
                headers=headers,
                params=current_params,
            )
            response.raise_for_status()
            data: dict[str, object] = response.json()

            value = data.get("value", [])
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        yield item

            next_link = data.get("@odata.nextLink")
            next_url = next_link if isinstance(next_link, str) else None
            current_params = None  # nextLink already carries query params

    async def _list_transcripts(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        meeting_id: str,
    ) -> list[dict[str, object]]:
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{_GRAPH_BASE}/me/onlineMeetings/{meeting_id}/transcripts"
        response = await self._request_with_retry(client, "GET", url, headers=headers)
        response.raise_for_status()
        data: dict[str, object] = response.json()
        value = data.get("value", [])
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    async def _fetch_vtt(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        meeting_id: str,
        transcript_id: str,
    ) -> str:
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{_GRAPH_BASE}/me/onlineMeetings/{meeting_id}/transcripts/{transcript_id}/content"
        params = {"$format": "text/vtt"}
        response = await self._request_with_retry(
            client, "GET", url, headers=headers, params=params
        )
        response.raise_for_status()
        return response.text

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Issue an HTTP request with exponential backoff on 429 responses.

        Retries up to 3 times (4 total attempts).  Delays: ~1s, ~2s, ~4s + jitter.
        Raises ``httpx.HTTPStatusError`` when all retries are exhausted.
        """
        max_retries = 3
        last_response: httpx.Response | None = None

        for attempt in range(max_retries + 1):
            last_response = await client.request(method, url, headers=headers, params=params)
            if last_response.status_code != 429:
                return last_response

            if attempt < max_retries:
                delay = (2.0**attempt) + random.uniform(0, 1)
                log.warning(
                    "ms_graph.rate_limited",
                    attempt=attempt,
                    delay=round(delay, 2),
                    url=url,
                )
                await asyncio.sleep(delay)

        # All retries exhausted — raise for the final 429
        if last_response is None:  # pragma: no cover
            raise RuntimeError("Unexpected state: no response after retry loop")
        raise httpx.HTTPStatusError(
            message=f"Rate limit exceeded after {max_retries} retries",
            request=last_response.request,
            response=last_response,
        )

    # ------------------------------------------------------------------
    # Private: document transformation
    # ------------------------------------------------------------------

    def _to_document(
        self, parsed: ParsedTranscript, *, join_web_url: str | None = None
    ) -> Document:
        """Transform a ParsedTranscript into the canonical Document schema (FR-5)."""
        now = datetime.datetime.now(tz=datetime.UTC)
        content = parsed.full_text or f"Meeting: {parsed.title}"
        doc_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"teams:{parsed.meeting_id}"))
        return Document(
            id=doc_id,
            content=content,
            metadata=DocumentMetadata(
                source_type=SourceType.TEAMS_TRANSCRIPT,
                source_id=parsed.meeting_id,
                title=f"Meeting: {parsed.title}",
                participants=parsed.participants,
                created_at=parsed.date,
                updated_at=parsed.date,
                synced_at=now,
                url=join_web_url,  # type: ignore[arg-type]
                custom={
                    "duration_minutes": parsed.duration_minutes,
                    "segments": [s.model_dump() for s in parsed.segments],
                },
            ),
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


class _MeetingMeta(TypedDict):
    title: str
    start_dt: datetime.datetime
    duration_minutes: int
    participants: list[str]
    join_web_url: str | None


def _parse_meeting_meta(meeting: dict[str, object]) -> _MeetingMeta:
    """Extract title, start_dt, duration_minutes, participants and join URL from a Graph meeting."""
    title = str(meeting.get("subject") or "Untitled Meeting")

    start_str = str(meeting.get("startDateTime") or "")
    end_str = str(meeting.get("endDateTime") or "")
    try:
        start_dt = _parse_graph_datetime(start_str)
        end_dt = _parse_graph_datetime(end_str)
        duration_minutes = max(0, int((end_dt - start_dt).total_seconds() / 60))
    except (ValueError, TypeError):
        log.warning(
            "teams_connector.unparseable_meeting_datetime",
            start_str=start_str,
            end_str=end_str,
        )
        start_dt = datetime.datetime.now(tz=datetime.UTC)
        duration_minutes = 0

    raw_attendees = meeting.get("attendees", [])
    participants: list[str] = []
    if isinstance(raw_attendees, list):
        for att in raw_attendees:
            if not isinstance(att, dict):
                continue
            identity = att.get("identity", {})
            if not isinstance(identity, dict):
                continue
            user = identity.get("user", {})
            if not isinstance(user, dict):
                continue
            name = user.get("displayName")
            if name and isinstance(name, str):
                participants.append(name)

    raw_join_url = meeting.get("joinWebUrl")
    join_web_url = str(raw_join_url) if isinstance(raw_join_url, str) and raw_join_url else None

    return _MeetingMeta(
        title=title,
        start_dt=start_dt,
        duration_minutes=duration_minutes,
        participants=participants,
        join_web_url=join_web_url,
    )


def _parse_graph_datetime(value: str) -> datetime.datetime:
    """Parse a Graph API ISO 8601 datetime string to a timezone-aware datetime."""
    if value.endswith("Z"):
        return datetime.datetime.fromisoformat(value[:-1]).replace(tzinfo=datetime.UTC)
    dt = datetime.datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.UTC)
    return dt
