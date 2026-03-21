"""JIRA Cloud Connector — ingests issues and comments via REST API v3.

Authenticates with email + API token (Basic auth).
Supports incremental sync via JQL `updated >=` filter.

Spec: F-011
NXP-85
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path
from typing import TypedDict, cast

import httpx
import structlog

from nexuspkm.config.models import JiraConnectorConfig
from nexuspkm.connectors.base import BaseConnector, ConnectorStatus
from nexuspkm.models.document import Document, DocumentMetadata, SourceType, SyncState

log = structlog.get_logger(__name__)

# Maximum number of consecutive 429 responses before aborting the page fetch.
_MAX_RATE_LIMIT_RETRIES = 5

_SEARCH_FIELDS = (
    "summary,description,status,assignee,reporter,priority,"
    "created,updated,labels,components,issuetype,comment,parent,"
    "customfield_10016,customfield_10020"
)


# ---------------------------------------------------------------------------
# State TypedDict
# ---------------------------------------------------------------------------


class _JiraIssueEntry(TypedDict):
    """Per-issue sync state entry."""

    doc_id: str
    updated: str  # ISO-8601 string from JIRA API


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


class JiraConnector(BaseConnector):
    """Ingests issues and comments from JIRA Cloud via REST API v3."""

    name = "jira"

    def __init__(self, state_dir: Path, config: JiraConnectorConfig) -> None:
        email = os.environ.get("JIRA_EMAIL")
        api_token = os.environ.get("JIRA_API_TOKEN")
        if not email:
            raise OSError("JIRA_EMAIL environment variable is required")
        if not api_token:
            raise OSError("JIRA_API_TOKEN environment variable is required")

        self._state_dir = state_dir
        self._config = config
        self._base_url = (config.base_url or "").rstrip("/")
        self._auth = httpx.BasicAuth(email, api_token)
        self._issue_state_file = state_dir / "jira_sync_state.json"
        self._checkpoint_file = state_dir / "jira_checkpoint.json"
        self._total_docs_synced = 0
        self._last_sync_errors: list[str] = []

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def jql_filter(self) -> str:
        return self._config.jql_filter

    @property
    def sync_interval_minutes(self) -> int:
        return self._config.sync_interval_minutes

    def update_sync_interval(self, minutes: int) -> None:
        self._config = JiraConnectorConfig(
            enabled=self._config.enabled,
            base_url=self._config.base_url,
            sync_interval_minutes=minutes,
            jql_filter=self._config.jql_filter,
        )

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    async def authenticate(self) -> bool:
        """Verify credentials via HEAD /rest/api/3/myself."""
        try:
            async with httpx.AsyncClient(auth=self._auth, timeout=10) as client:
                resp = await client.get(f"{self._base_url}/rest/api/3/myself")
                resp.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            log.warning("jira_connector.authenticate_failed", error=str(exc))
            return False

    def fetch(self, since: datetime.datetime | None = None) -> AsyncIterator[Document]:
        return self._fetch_gen(since)

    async def fetch_deleted_ids(self, since: datetime.datetime | None = None) -> list[str]:
        """Return doc IDs for issues that returned 404 since last sync."""
        _ = since
        issue_state = await self._load_issue_state()
        if not issue_state:
            return []

        deleted_ids: list[str] = []
        updated_state: dict[str, _JiraIssueEntry] = {}

        async with httpx.AsyncClient(auth=self._auth, timeout=15) as client:
            for issue_key, entry in issue_state.items():
                try:
                    resp = await client.get(
                        f"{self._base_url}/rest/api/3/issue/{issue_key}",
                        params={"fields": "summary"},
                    )
                    resp.raise_for_status()
                    updated_state[issue_key] = entry
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        deleted_ids.append(entry["doc_id"])
                        log.info(
                            "jira_connector.issue_deleted",
                            issue_key=issue_key,
                            doc_id=entry["doc_id"],
                        )
                    else:
                        updated_state[issue_key] = entry
                except httpx.HTTPError:
                    updated_state[issue_key] = entry

        if deleted_ids:
            await self._save_issue_state(updated_state)

        return deleted_ids

    async def health_check(self) -> ConnectorStatus:
        return ConnectorStatus(
            name=self.name,
            status="healthy" if not self._last_sync_errors else "degraded",
            documents_synced=self._total_docs_synced,
            sync_errors=list(self._last_sync_errors),
        )

    async def get_sync_state(self) -> SyncState:
        checkpoint_file = self._checkpoint_file

        def _read() -> SyncState:
            if not checkpoint_file.exists():
                return SyncState()
            try:
                data = json.loads(checkpoint_file.read_text())
                return SyncState.model_validate(data)
            except (json.JSONDecodeError, ValueError):
                log.warning(
                    "jira_connector.checkpoint_load_failed",
                    path=str(checkpoint_file),
                )
                return SyncState()

        return await asyncio.to_thread(_read)

    async def restore_sync_state(self, state: SyncState) -> None:
        checkpoint_file = self._checkpoint_file
        serialized = state.model_dump_json()

        def _write() -> None:
            checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
            checkpoint_file.write_text(serialized)

        await asyncio.to_thread(_write)

    # ------------------------------------------------------------------
    # Private: fetch pipeline
    # ------------------------------------------------------------------

    async def _fetch_gen(self, since: datetime.datetime | None) -> AsyncGenerator[Document, None]:
        self._last_sync_errors = []
        issue_state = await self._load_issue_state()
        jql = self._build_jql(since)

        try:
            async with httpx.AsyncClient(auth=self._auth, timeout=30) as client:
                start_at = 0
                total: int | None = None
                rate_limit_retries = 0

                while True:
                    params: dict[str, str | int] = {
                        "jql": jql,
                        "fields": _SEARCH_FIELDS,
                        "maxResults": 100,
                        "startAt": start_at,
                    }
                    try:
                        resp = await client.get(
                            f"{self._base_url}/rest/api/3/search",
                            params=params,
                        )
                        if resp.status_code == 429:
                            rate_limit_retries += 1
                            if rate_limit_retries > _MAX_RATE_LIMIT_RETRIES:
                                err = f"rate limit exceeded after {_MAX_RATE_LIMIT_RETRIES} retries"
                                self._last_sync_errors.append(err)
                                log.error("jira_connector.rate_limit_retries_exhausted")
                                return
                            retry_after = int(resp.headers.get("Retry-After", "5"))
                            log.warning(
                                "jira_connector.rate_limited",
                                retry_after=retry_after,
                                attempt=rate_limit_retries,
                            )
                            await asyncio.sleep(retry_after)
                            continue
                        rate_limit_retries = 0  # reset on successful response
                        resp.raise_for_status()
                    except httpx.HTTPError as exc:
                        self._last_sync_errors.append(str(exc))
                        log.error("jira_connector.search_failed", error=str(exc), exc_info=True)
                        break

                    data = resp.json()
                    issues = data.get("issues", [])
                    if total is None:
                        total = data.get("total", 0)

                    for issue in issues:
                        issue_key: str = issue.get("key", "")
                        updated_str: str = issue.get("fields", {}).get("updated", "")

                        existing = issue_state.get(issue_key)
                        if existing is not None and existing["updated"] == updated_str:
                            continue

                        try:
                            doc = self._to_document(issue)
                            issue_state[issue_key] = _JiraIssueEntry(
                                doc_id=doc.id, updated=updated_str
                            )
                            self._total_docs_synced += 1
                            yield doc
                        except Exception as exc:
                            self._last_sync_errors.append(f"{issue_key}: {exc}")
                            log.warning(
                                "jira_connector.issue_transform_failed",
                                issue_key=issue_key,
                                exc_info=True,
                            )

                    start_at += len(issues)
                    if not issues or start_at >= (total or 0):
                        break
        finally:
            await self._save_issue_state(issue_state)

    # ------------------------------------------------------------------
    # Private: JQL
    # ------------------------------------------------------------------

    def _build_jql(self, since: datetime.datetime | None) -> str:
        base = self._config.jql_filter
        if since is None:
            return base
        date_str = since.strftime("%Y-%m-%d %H:%M")
        return f'{base} AND updated >= "{date_str}"'

    # ------------------------------------------------------------------
    # Private: document transformation
    # ------------------------------------------------------------------

    def _to_document(self, issue: dict[str, object]) -> Document:
        fields = cast(dict[str, object], issue.get("fields", {}))
        key: str = str(issue.get("key", ""))
        summary: str = str(fields.get("summary") or "")

        description = fields.get("description") or ""
        description_text = str(description) if description else ""

        # Comments
        comment_block = cast(dict[str, object], fields.get("comment") or {})
        raw_comments = cast(list[dict[str, object]], comment_block.get("comments") or [])
        comments_text = self._format_comments(raw_comments)

        content = f"{key}: {summary}"
        if description_text:
            content += f"\n\n{description_text}"
        if comments_text:
            content += f"\n\n{comments_text}"

        # Timestamps
        created_str = str(fields.get("created") or "")
        updated_str = str(fields.get("updated") or "")
        now = datetime.datetime.now(tz=datetime.UTC)
        created_at = _parse_jira_datetime(created_str) if created_str else now
        updated_at = _parse_jira_datetime(updated_str) if updated_str else now
        if updated_at < created_at:
            updated_at = created_at

        # People
        reporter_obj = cast(dict[str, object] | None, fields.get("reporter"))
        assignee_obj = cast(dict[str, object] | None, fields.get("assignee"))
        reporter_name = str(reporter_obj["displayName"]) if reporter_obj else None
        assignee_name = str(assignee_obj["displayName"]) if assignee_obj else None

        # Tags
        raw_labels = cast(list[object], fields.get("labels") or [])
        labels = [str(lb) for lb in raw_labels]
        raw_components = cast(list[dict[str, object]], fields.get("components") or [])
        component_names = [str(c.get("name", "")) for c in raw_components]
        tags = labels + [f"component:{c}" for c in component_names]

        # Custom fields
        status_obj = cast(dict[str, object] | None, fields.get("status"))
        issue_type_obj = cast(dict[str, object] | None, fields.get("issuetype"))
        priority_obj = cast(dict[str, object] | None, fields.get("priority"))
        parent_obj = cast(dict[str, object] | None, fields.get("parent"))
        parent_key = str(parent_obj["key"]) if parent_obj else None

        # Sprint (customfield_10020 is a list of sprint objects in Jira Cloud)
        sprints = cast(list[dict[str, object]] | None, fields.get("customfield_10020"))
        sprint_name: str | None = None
        if sprints:
            sprint_name = str(sprints[-1].get("name", "")) or None

        story_points_raw = fields.get("customfield_10016")
        story_points = (
            float(story_points_raw) if isinstance(story_points_raw, (int, float)) else None
        )

        doc_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"jira_issue:{key}"))

        return Document(
            id=doc_id,
            content=content,
            metadata=DocumentMetadata(
                source_type=SourceType.JIRA_ISSUE,
                source_id=key,
                title=f"{key}: {summary}",
                author=reporter_name,
                tags=tags,
                url=f"{self._base_url}/browse/{key}",  # type: ignore[arg-type]
                created_at=created_at,
                updated_at=updated_at,
                synced_at=now,
                custom={
                    "issue_type": str(issue_type_obj["name"]) if issue_type_obj else None,
                    "status": str(status_obj["name"]) if status_obj else None,
                    "priority": str(priority_obj["name"]) if priority_obj else None,
                    "assignee": assignee_name,
                    "reporter": reporter_name,
                    "sprint": sprint_name,
                    "parent_key": parent_key,
                    "components": component_names,
                    "story_points": story_points,
                },
            ),
        )

    def _format_comments(self, comments: list[dict[str, object]]) -> str:
        lines: list[str] = []
        for comment in comments:
            author_obj = cast(dict[str, object] | None, comment.get("author"))
            author = str(author_obj["displayName"]) if author_obj else "Unknown"
            body = str(comment.get("body") or "")
            created_str = str(comment.get("created") or "")
            date_part = ""
            if created_str:
                try:
                    dt = _parse_jira_datetime(created_str)
                    date_part = dt.strftime("%Y-%m-%d")
                except ValueError:
                    date_part = ""
            if date_part:
                lines.append(f"[{author} - {date_part}]: {body}")
            else:
                lines.append(f"[{author}]: {body}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private: issue state persistence
    # ------------------------------------------------------------------

    async def _load_issue_state(self) -> dict[str, _JiraIssueEntry]:
        state_file = self._issue_state_file

        def _read() -> dict[str, _JiraIssueEntry]:
            if not state_file.exists():
                return {}
            try:
                raw = json.loads(state_file.read_text())
                if not isinstance(raw, dict):
                    return {}
                return {
                    k: cast(_JiraIssueEntry, v)
                    for k, v in raw.items()
                    if isinstance(v, dict)
                    and isinstance(v.get("doc_id"), str)
                    and isinstance(v.get("updated"), str)
                }
            except (json.JSONDecodeError, ValueError, TypeError):
                log.warning("jira_connector.state_load_failed", path=str(state_file))
                return {}

        return await asyncio.to_thread(_read)

    async def _save_issue_state(self, state: dict[str, _JiraIssueEntry]) -> None:
        state_file = self._issue_state_file
        serialized = json.dumps({k: dict(v) for k, v in state.items()}, indent=2)

        def _write() -> None:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = state_file.with_suffix(".tmp")
            tmp.write_text(serialized)
            tmp.replace(state_file)

        await asyncio.to_thread(_write)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_jira_datetime(value: str) -> datetime.datetime:
    """Parse a JIRA ISO 8601 datetime string to a timezone-aware datetime.

    JIRA Cloud returns strings like ``2026-01-01T10:00:00.000+0000`` or
    ``2026-01-01T10:00:00.000+0530``.
    """
    # Normalize +0000 → +00:00 for fromisoformat compatibility
    if len(value) > 5 and value[-5] in ("+", "-") and ":" not in value[-5:]:
        value = value[:-2] + ":" + value[-2:]
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.datetime.fromisoformat(value)
