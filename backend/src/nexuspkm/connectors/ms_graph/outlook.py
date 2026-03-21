"""Outlook Email and Calendar Connector.

Fetches emails and calendar events via Microsoft Graph API.

Authenticates via Device Code Flow (delegated), uses delta queries for incremental
email sync, groups emails by conversationId into thread documents, and fetches
calendar events within a configurable window.

Spec: F-010
NXP-69
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import json
import random
import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path

import html2text as _html2text
import httpx
import structlog

from nexuspkm.config.models import OutlookConnectorConfig
from nexuspkm.connectors.base import BaseConnector, ConnectorStatus
from nexuspkm.connectors.ms_graph.auth import AuthFlowContext, DeviceCodeInfo, MicrosoftGraphAuth
from nexuspkm.models.document import Document, DocumentMetadata, SourceType, SyncState

log = structlog.get_logger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------


def _html_to_text(html: str) -> str:
    """Convert HTML to plain text using html2text."""
    if not html:
        return ""
    converter = _html2text.HTML2Text()
    converter.body_width = 0
    converter.ignore_images = True
    converter.unicode_snob = True
    converter.ignore_links = True
    return converter.handle(html).strip()


def _parse_graph_datetime(value: str) -> datetime.datetime:
    """Parse a Graph API ISO 8601 datetime string to a timezone-aware datetime."""
    if value.endswith("Z"):
        return datetime.datetime.fromisoformat(value[:-1]).replace(tzinfo=datetime.UTC)
    dt = datetime.datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.UTC)
    return dt


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


class OutlookConnector(BaseConnector):
    """Ingests Outlook emails (threaded) and calendar events via the Graph API."""

    name = "outlook"

    def __init__(
        self,
        token_dir: Path,
        state_dir: Path,
        config: OutlookConnectorConfig,
    ) -> None:
        self._auth = MicrosoftGraphAuth(token_dir)
        self._state_file = state_dir / "outlook_sync_state.json"
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
        """Start the Microsoft Graph Device Code auth flow."""
        return await self._auth.initiate_device_code_flow()

    async def complete_auth_flow(self, context: AuthFlowContext) -> bool:
        """Poll for token after device code authentication."""
        return await self._auth.poll_for_token(context)

    def fetch(self, since: datetime.datetime | None = None) -> AsyncIterator[Document]:
        """Return an async iterator of Documents for emails and calendar events."""
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
                log.warning("outlook_connector.state_load_failed", path=str(state_file))
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

    @property
    def config(self) -> OutlookConnectorConfig:
        """Return the current connector configuration."""
        return self._config

    def update_config(self, **kwargs: object) -> None:
        """Update connector configuration fields at runtime.

        Only fields present in ``kwargs`` are updated; others are unchanged.
        Uses ``model_copy`` so Pydantic validation is preserved.
        """
        self._config = self._config.model_copy(update=kwargs)

    async def fetch_deleted_ids(self, since: datetime.datetime | None = None) -> list[str]:
        """Return conversation IDs deleted via delta response."""
        state = await self.get_sync_state()
        raw = state.extra.get("deleted_source_ids", [])
        if isinstance(raw, list):
            return [str(item) for item in raw]
        return []

    # ------------------------------------------------------------------
    # Private: fetch pipeline
    # ------------------------------------------------------------------

    async def _fetch_gen(self, since: datetime.datetime | None) -> AsyncGenerator[Document, None]:
        access_token = await self._auth.get_access_token()
        if access_token is None:
            log.warning("outlook_connector.no_token_skipping_fetch")
            return

        state = await self.get_sync_state()
        raw_delta = state.extra.get("email_delta_token")
        delta_token: str | None = raw_delta if isinstance(raw_delta, str) else None

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            email_docs, new_delta_token, deleted_conv_ids = await self._fetch_emails(
                client, access_token, delta_token
            )
            calendar_docs = await self._fetch_calendar(client, access_token)

        for doc in email_docs:
            self._total_docs_synced += 1
            yield doc

        for doc in calendar_docs:
            self._total_docs_synced += 1
            yield doc

        # Persist updated state
        extra: dict[str, object] = dict(state.extra)
        if new_delta_token is not None:
            extra["email_delta_token"] = new_delta_token

        # Accumulate deleted conversation IDs
        if deleted_conv_ids:
            raw_existing = extra.get("deleted_source_ids", [])
            existing: list[str] = (
                [str(x) for x in raw_existing] if isinstance(raw_existing, list) else []
            )
            extra["deleted_source_ids"] = list({*existing, *deleted_conv_ids})

        now = datetime.datetime.now(tz=datetime.UTC)
        new_state = SyncState(
            last_synced_at=now,
            documents_synced=state.documents_synced + len(email_docs) + len(calendar_docs),
            extra=extra,
        )
        await self.restore_sync_state(new_state)

    # ------------------------------------------------------------------
    # Private: email pipeline
    # ------------------------------------------------------------------

    async def _fetch_emails(
        self,
        client: httpx.AsyncClient,
        token: str,
        delta_token: str | None,
    ) -> tuple[list[Document], str | None, list[str]]:
        """Fetch emails via delta query, apply filters, group into thread docs.

        Returns (email_docs, new_delta_token, deleted_conversation_ids).
        """
        raw_emails, new_delta_token, deleted_conv_ids = await self._list_emails_delta(
            client, token, delta_token
        )

        # Build a folder name cache to avoid repeated lookups
        folder_cache: dict[str, str] = {}

        filtered_emails: list[dict[str, object]] = []
        for email in raw_emails:
            folder_id = str(email.get("parentFolderId", ""))
            if folder_id not in folder_cache:
                folder_name = await self._get_folder_name(client, token, folder_id)
                folder_cache[folder_id] = folder_name
            folder_name = folder_cache[folder_id]
            if self._apply_email_filters(email, folder_name=folder_name):
                filtered_emails.append(email)

        # Enforce max_emails_per_sync
        if len(filtered_emails) > self._config.max_emails_per_sync:
            filtered_emails = filtered_emails[: self._config.max_emails_per_sync]

        docs = self._build_thread_documents(filtered_emails)
        return docs, new_delta_token, deleted_conv_ids

    async def _fetch_calendar(
        self,
        client: httpx.AsyncClient,
        token: str,
    ) -> list[Document]:
        """Fetch calendar events within the configured window."""
        now = datetime.datetime.now(tz=datetime.UTC)
        window = datetime.timedelta(days=self._config.calendar_window_days)
        start = now - window
        end = now + window

        events = await self._list_calendar_events(client, token, start, end)
        return [self._to_calendar_document(event) for event in events]

    async def _list_emails_delta(
        self,
        client: httpx.AsyncClient,
        token: str,
        delta_token: str | None,
    ) -> tuple[list[dict[str, object]], str | None, list[str]]:
        """Paginate the delta query for emails.

        Returns (emails, new_delta_token, deleted_conversation_ids).
        """
        headers = {"Authorization": f"Bearer {token}"}

        if delta_token:
            # Resume from previous delta link
            next_url: str | None = f"{_GRAPH_BASE}/me/messages/delta?$deltaToken={delta_token}"
            params: dict[str, str] | None = None
        else:
            next_url = f"{_GRAPH_BASE}/me/messages/delta"
            params = {
                "$top": "100",
                "$select": (
                    "id,conversationId,subject,body,sender,"
                    "toRecipients,ccRecipients,receivedDateTime,"
                    "parentFolderId,isRead"
                ),
            }

        all_emails: list[dict[str, object]] = []
        deleted_conv_ids: list[str] = []
        new_delta_token: str | None = None
        max_emails = self._config.max_emails_per_sync

        while next_url is not None:
            response = await self._request_with_retry(
                client, "GET", next_url, headers=headers, params=params
            )
            response.raise_for_status()
            data: dict[str, object] = response.json()

            value = data.get("value", [])
            if isinstance(value, list):
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    if "@removed" in item:
                        # Graph only guarantees `id` on removed items; `conversationId`
                        # may be absent. Log a warning when it is so the deletion isn't
                        # silently swallowed.
                        conv_id = str(item.get("conversationId", ""))
                        if conv_id:
                            deleted_conv_ids.append(conv_id)
                        else:
                            msg_id = str(item.get("id", "<unknown>"))
                            log.warning(
                                "outlook_connector.removed_item_missing_conversation_id",
                                message_id=msg_id,
                            )
                    elif len(all_emails) < max_emails:
                        all_emails.append(item)

            delta_link = data.get("@odata.deltaLink")
            if isinstance(delta_link, str) and delta_link:
                # Extract delta token from delta link
                if "$deltaToken=" in delta_link:
                    new_delta_token = delta_link.split("$deltaToken=")[-1]
                else:
                    new_delta_token = delta_link
                next_url = None
            else:
                next_link = data.get("@odata.nextLink")
                next_url = next_link if isinstance(next_link, str) else None
                params = None  # nextLink already carries query params

        return all_emails, new_delta_token, deleted_conv_ids

    async def _list_calendar_events(
        self,
        client: httpx.AsyncClient,
        token: str,
        start: datetime.datetime,
        end: datetime.datetime,
    ) -> list[dict[str, object]]:
        """Paginate calendarView for events within [start, end]."""
        headers = {"Authorization": f"Bearer {token}"}
        start_str = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end.strftime("%Y-%m-%dT%H:%M:%SZ")

        url = f"{_GRAPH_BASE}/me/calendarView"
        params: dict[str, str] | None = {
            "startDateTime": start_str,
            "endDateTime": end_str,
            "$top": "100",
            "$select": (
                "id,subject,start,end,body,organizer,attendees,isOnlineMeeting,recurrence,webLink"
            ),
        }
        next_url: str | None = url
        all_events: list[dict[str, object]] = []

        while next_url is not None:
            response = await self._request_with_retry(
                client, "GET", next_url, headers=headers, params=params
            )
            response.raise_for_status()
            data: dict[str, object] = response.json()

            value = data.get("value", [])
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        all_events.append(item)

            next_link = data.get("@odata.nextLink")
            next_url = next_link if isinstance(next_link, str) else None
            params = None

        return all_events

    async def _get_folder_name(
        self,
        client: httpx.AsyncClient,
        token: str,
        folder_id: str,
    ) -> str:
        """Look up a mail folder's displayName. Returns empty string on error."""
        if not folder_id:
            return ""
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{_GRAPH_BASE}/me/mailFolders/{folder_id}"
        try:
            response = await self._request_with_retry(client, "GET", url, headers=headers)
            if response.status_code == 200:
                data: dict[str, object] = response.json()
                name = data.get("displayName", "")
                return str(name) if name else ""
        except Exception:
            log.warning(
                "outlook_connector.folder_lookup_failed",
                folder_id=folder_id,
                exc_info=True,
            )
        return ""

    # ------------------------------------------------------------------
    # Private: filters
    # ------------------------------------------------------------------

    def _apply_email_filters(
        self,
        email: dict[str, object],
        folder_name: str = "",
    ) -> bool:
        """Return True if the email passes all configured filters."""
        # Folder allow-list
        if self._config.folders and folder_name not in self._config.folders:
            return False

        # Folder exclude-list
        if folder_name in self._config.exclude_folders:
            return False

        # Sender domain filter
        if self._config.sender_domains:
            sender_raw = email.get("sender", {})
            if isinstance(sender_raw, dict):
                addr_raw = sender_raw.get("emailAddress", {})
                if isinstance(addr_raw, dict):
                    address = str(addr_raw.get("address", ""))
                    domain = address.split("@")[-1] if "@" in address else ""
                    if domain not in self._config.sender_domains:
                        return False

        # Date filter
        if self._config.date_from:
            received_str = str(email.get("receivedDateTime", ""))
            if received_str:
                try:
                    received_dt = _parse_graph_datetime(received_str)
                    date_from = datetime.datetime.fromisoformat(self._config.date_from).replace(
                        tzinfo=datetime.UTC
                    )
                    if received_dt < date_from:
                        return False
                except (ValueError, TypeError):
                    pass

        return True

    # ------------------------------------------------------------------
    # Private: document building
    # ------------------------------------------------------------------

    def _build_thread_documents(self, emails: list[dict[str, object]]) -> list[Document]:
        """Group emails by conversationId and produce one Document per thread."""
        threads: dict[str, list[dict[str, object]]] = defaultdict(list)
        for email in emails:
            conv_id = str(email.get("conversationId", ""))
            if conv_id:
                threads[conv_id].append(email)

        return [self._to_email_thread_document(thread_emails) for thread_emails in threads.values()]

    def _to_email_thread_document(self, thread_emails: list[dict[str, object]]) -> Document:
        """Convert a list of emails sharing a conversationId into a Document."""
        now = datetime.datetime.now(tz=datetime.UTC)
        conv_id = str(thread_emails[0].get("conversationId", ""))

        # Collect participants from all emails in the thread
        participants: set[str] = set()
        for email in thread_emails:
            sender_raw = email.get("sender", {})
            if isinstance(sender_raw, dict):
                addr_raw = sender_raw.get("emailAddress", {})
                if isinstance(addr_raw, dict):
                    addr = str(addr_raw.get("address", ""))
                    if addr:
                        participants.add(addr)
            for field in ("toRecipients", "ccRecipients"):
                recipients = email.get(field, [])
                if isinstance(recipients, list):
                    for rec in recipients:
                        if not isinstance(rec, dict):
                            continue
                        addr_raw = rec.get("emailAddress", {})
                        if isinstance(addr_raw, dict):
                            addr = str(addr_raw.get("address", ""))
                            if addr:
                                participants.add(addr)

        # Sort by receivedDateTime; most recent = updated_at
        def _received(e: dict[str, object]) -> datetime.datetime:
            val = str(e.get("receivedDateTime", ""))
            try:
                return _parse_graph_datetime(val)
            except (ValueError, TypeError):
                return now

        sorted_emails = sorted(thread_emails, key=_received)
        created_at = _received(sorted_emails[0])
        updated_at = _received(sorted_emails[-1])

        # Use the most recent email's subject as the thread title
        latest_subject = str(sorted_emails[-1].get("subject", "") or "No Subject")
        # Strip common reply/forward prefixes
        title = latest_subject.lstrip()
        for prefix in ("Re: ", "RE: ", "Fwd: ", "FWD: ", "Fw: "):
            if title.startswith(prefix):
                title = title[len(prefix) :]
                break

        # Build content from all emails
        parts: list[str] = []
        for email in sorted_emails:
            email_subject = str(email.get("subject", "") or "")
            sender_raw = email.get("sender", {})
            sender_addr = ""
            if isinstance(sender_raw, dict):
                addr_raw = sender_raw.get("emailAddress", {})
                if isinstance(addr_raw, dict):
                    sender_addr = str(addr_raw.get("address", ""))
            body_raw = email.get("body", {})
            body_text = ""
            if isinstance(body_raw, dict):
                content = str(body_raw.get("content", ""))
                content_type = str(body_raw.get("contentType", "html"))
                body_text = _html_to_text(content) if content_type.lower() == "html" else content

            received_str = str(email.get("receivedDateTime", ""))
            header = f"From: {sender_addr}\nDate: {received_str}\nSubject: {email_subject}"
            parts.append(f"{header}\n\n{body_text}")

        content = "\n\n---\n\n".join(parts) or f"Email Thread: {title}"

        doc_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"outlook_email:{conv_id}"))

        return Document(
            id=doc_id,
            content=content,
            metadata=DocumentMetadata(
                source_type=SourceType.OUTLOOK_EMAIL,
                source_id=conv_id,
                title=f"Email: {title}",
                participants=sorted(participants),
                created_at=created_at,
                updated_at=updated_at,
                synced_at=now,
                custom={
                    "email_count": len(thread_emails),
                    "conversation_id": conv_id,
                },
            ),
        )

    def _to_calendar_document(self, event: dict[str, object]) -> Document:
        """Convert a Graph calendar event into a Document."""
        now = datetime.datetime.now(tz=datetime.UTC)
        event_id = str(event.get("id", ""))
        subject = str(event.get("subject", "") or "No Title")

        start_raw = event.get("start", {})
        end_raw = event.get("end", {})
        start_dt = now
        end_dt = now
        if isinstance(start_raw, dict):
            with contextlib.suppress(ValueError, TypeError):
                start_dt = _parse_graph_datetime(str(start_raw.get("dateTime", "")))
        if isinstance(end_raw, dict):
            with contextlib.suppress(ValueError, TypeError):
                end_dt = _parse_graph_datetime(str(end_raw.get("dateTime", "")))

        # Participants: organizer + attendees
        participants: list[str] = []
        organizer_raw = event.get("organizer", {})
        if isinstance(organizer_raw, dict):
            addr_raw = organizer_raw.get("emailAddress", {})
            if isinstance(addr_raw, dict):
                addr = str(addr_raw.get("address", ""))
                if addr:
                    participants.append(addr)

        attendees_raw = event.get("attendees", [])
        if isinstance(attendees_raw, list):
            for att in attendees_raw:
                if not isinstance(att, dict):
                    continue
                addr_raw = att.get("emailAddress", {})
                if isinstance(addr_raw, dict):
                    addr = str(addr_raw.get("address", ""))
                    if addr and addr not in participants:
                        participants.append(addr)

        # Body content
        body_raw = event.get("body", {})
        body_text = ""
        if isinstance(body_raw, dict):
            content = str(body_raw.get("content", ""))
            content_type = str(body_raw.get("contentType", "html"))
            body_text = _html_to_text(content) if content_type.lower() == "html" else content

        content_str = body_text or f"Calendar Event: {subject}"

        is_online_meeting = bool(event.get("isOnlineMeeting", False))
        is_recurring = event.get("recurrence") is not None

        web_link_raw = event.get("webLink")
        web_link = str(web_link_raw) if isinstance(web_link_raw, str) and web_link_raw else None

        duration_minutes = max(0, int((end_dt - start_dt).total_seconds() / 60))
        doc_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"outlook_calendar:{event_id}"))

        return Document(
            id=doc_id,
            content=content_str,
            metadata=DocumentMetadata(
                source_type=SourceType.OUTLOOK_CALENDAR,
                source_id=event_id,
                title=f"Calendar: {subject}",
                participants=participants,
                created_at=start_dt,
                updated_at=start_dt,
                synced_at=now,
                url=web_link,  # type: ignore[arg-type]
                custom={
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                    "duration_minutes": duration_minutes,
                    "is_online_meeting": is_online_meeting,
                    "is_recurring": is_recurring,
                },
            ),
        )

    # ------------------------------------------------------------------
    # Private: HTTP with retry
    # ------------------------------------------------------------------

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
