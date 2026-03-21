"""Unit tests for JiraConnector.

Covers: connectors/jira/connector.py
Spec: F-011
NXP-85
"""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from nexuspkm.config.models import JiraConnectorConfig
from nexuspkm.connectors.jira.connector import JiraConnector, _JiraIssueEntry
from nexuspkm.models.document import SourceType


def _make_connector(tmp_path: Path, **kwargs: object) -> JiraConnector:
    config = JiraConnectorConfig(
        enabled=True,
        base_url="https://example.atlassian.net",
        **kwargs,  # type: ignore[arg-type]
    )
    with patch.dict("os.environ", {"JIRA_EMAIL": "user@example.com", "JIRA_API_TOKEN": "token"}):
        return JiraConnector(state_dir=tmp_path / "state", config=config)


def _make_issue(
    key: str = "PROJ-1",
    summary: str = "Test Issue",
    description: str = "Description text",
    status: str = "In Progress",
    issue_type: str = "Story",
    priority: str = "Medium",
    reporter: str = "Alice Smith",
    assignee: str = "Bob Jones",
    labels: list[str] | None = None,
    components: list[str] | None = None,
    created: str = "2026-01-01T10:00:00.000+0000",
    updated: str = "2026-01-02T12:00:00.000+0000",
    comments: list[dict[str, object]] | None = None,
    parent_key: str | None = None,
    sprint_name: str | None = None,
    story_points: float | None = None,
) -> dict[str, object]:
    issue: dict[str, object] = {
        "id": "10001",
        "key": key,
        "fields": {
            "summary": summary,
            "description": description,
            "status": {"name": status},
            "issuetype": {"name": issue_type},
            "priority": {"name": priority},
            "reporter": {"displayName": reporter},
            "assignee": {"displayName": assignee},
            "labels": labels or [],
            "components": [{"name": c} for c in (components or [])],
            "created": created,
            "updated": updated,
            "comment": {
                "comments": comments or [],
            },
            "parent": {"key": parent_key} if parent_key else None,
            "customfield_10016": story_points,
        },
    }
    if sprint_name is not None:
        issue["fields"]["customfield_10020"] = [{"name": sprint_name}]  # type: ignore[index]
    else:
        issue["fields"]["customfield_10020"] = None  # type: ignore[index]
    return issue


def _make_comment(
    author: str = "Alice Smith",
    body: str = "Comment text",
    created: str = "2026-01-01T11:00:00.000+0000",
) -> dict[str, object]:
    return {
        "author": {"displayName": author},
        "body": body,
        "created": created,
    }


def _make_search_response(
    issues: list[dict[str, object]],
    total: int | None = None,
    start_at: int = 0,
) -> dict[str, object]:
    return {
        "issues": issues,
        "total": total if total is not None else len(issues),
        "startAt": start_at,
        "maxResults": 100,
    }


# ---------------------------------------------------------------------------
# JQL construction
# ---------------------------------------------------------------------------


def test_jql_without_since(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path, jql_filter="project = PROJ")
    jql = connector._build_jql(since=None)
    assert jql == "project = PROJ"


def test_jql_with_since(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path, jql_filter="project = PROJ")
    since = datetime.datetime(2026, 1, 1, 0, 0, 0, tzinfo=datetime.UTC)
    jql = connector._build_jql(since=since)
    # Should append an updated >= filter
    assert "project = PROJ" in jql
    assert "updated >=" in jql
    assert "2026-01-01" in jql


def test_jql_default_filter(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    jql = connector._build_jql(since=None)
    assert "currentUser()" in jql


# ---------------------------------------------------------------------------
# Issue-to-Document transformation
# ---------------------------------------------------------------------------


def test_to_document_basic_fields(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    issue = _make_issue(
        key="NXP-1",
        summary="My Ticket",
        description="Do the thing",
        status="Open",
        issue_type="Task",
        priority="High",
        reporter="Alice",
        assignee="Bob",
    )
    doc = connector._to_document(issue)

    assert doc.metadata.source_type == SourceType.JIRA_ISSUE
    assert doc.metadata.source_id == "NXP-1"
    assert doc.metadata.title == "NXP-1: My Ticket"
    assert doc.metadata.author == "Alice"
    assert "NXP-1: My Ticket" in doc.content
    assert "Do the thing" in doc.content
    assert str(doc.metadata.url) == "https://example.atlassian.net/browse/NXP-1"


def test_to_document_stable_doc_id(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    issue = _make_issue(key="PROJ-42")
    doc1 = connector._to_document(issue)
    doc2 = connector._to_document(issue)
    assert doc1.id == doc2.id
    expected = str(uuid.uuid5(uuid.NAMESPACE_OID, "jira_issue:PROJ-42"))
    assert doc1.id == expected


def test_to_document_tags_from_labels_and_components(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    issue = _make_issue(
        labels=["backend", "urgent"],
        components=["Auth", "API"],
    )
    doc = connector._to_document(issue)
    assert "backend" in doc.metadata.tags
    assert "urgent" in doc.metadata.tags
    assert "component:Auth" in doc.metadata.tags
    assert "component:API" in doc.metadata.tags


def test_to_document_custom_fields(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    issue = _make_issue(
        status="Done",
        issue_type="Bug",
        priority="Critical",
        assignee="Carol",
        reporter="Dave",
        parent_key="PROJ-10",
        components=["Core"],
        story_points=3.0,
    )
    doc = connector._to_document(issue)
    custom = doc.metadata.custom
    assert custom["status"] == "Done"
    assert custom["issue_type"] == "Bug"
    assert custom["priority"] == "Critical"
    assert custom["assignee"] == "Carol"
    assert custom["reporter"] == "Dave"
    assert custom["parent_key"] == "PROJ-10"
    assert custom["components"] == ["Core"]
    assert custom["story_points"] == 3.0


def test_to_document_sprint_name(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    issue = _make_issue(sprint_name="Sprint 5")
    doc = connector._to_document(issue)
    assert doc.metadata.custom["sprint"] == "Sprint 5"


def test_to_document_no_sprint(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    issue = _make_issue()
    doc = connector._to_document(issue)
    assert doc.metadata.custom["sprint"] is None


def test_to_document_empty_description(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    issue = _make_issue(description="", summary="Only Summary")
    doc = connector._to_document(issue)
    # Content should still contain the key and summary
    assert "Only Summary" in doc.content
    assert doc.content  # non-empty


def test_to_document_null_description(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    issue = _make_issue(summary="Null Desc")
    issue["fields"]["description"] = None  # type: ignore[index]
    doc = connector._to_document(issue)
    assert "Null Desc" in doc.content


def test_to_document_null_assignee(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    issue = _make_issue()
    issue["fields"]["assignee"] = None  # type: ignore[index]
    doc = connector._to_document(issue)
    assert doc.metadata.custom["assignee"] is None


def test_to_document_null_reporter(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    issue = _make_issue()
    issue["fields"]["reporter"] = None  # type: ignore[index]
    doc = connector._to_document(issue)
    assert doc.metadata.author is None


def test_to_document_null_priority(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    issue = _make_issue()
    issue["fields"]["priority"] = None  # type: ignore[index]
    doc = connector._to_document(issue)
    assert doc.metadata.custom["priority"] is None


# ---------------------------------------------------------------------------
# Comment formatting
# ---------------------------------------------------------------------------


def test_to_document_includes_comments(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    comments = [
        _make_comment(author="Alice", body="First comment", created="2026-01-01T11:00:00.000+0000"),
        _make_comment(author="Bob", body="Second comment", created="2026-01-01T12:00:00.000+0000"),
    ]
    issue = _make_issue(comments=comments)
    doc = connector._to_document(issue)
    assert "Alice" in doc.content
    assert "First comment" in doc.content
    assert "Bob" in doc.content
    assert "Second comment" in doc.content


def test_comment_format(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    comments = [
        _make_comment(author="Carol", body="Hello world", created="2026-03-15T09:00:00.000+0000"),
    ]
    issue = _make_issue(comments=comments)
    doc = connector._to_document(issue)
    assert "[Carol - 2026-03-15]: Hello world" in doc.content


def test_empty_comments(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    issue = _make_issue(comments=[])
    doc = connector._to_document(issue)
    # Should not raise; content still valid
    assert doc.content


# ---------------------------------------------------------------------------
# Incremental skip logic
# ---------------------------------------------------------------------------


async def test_incremental_skip_unchanged_issue(tmp_path: Path) -> None:
    """Issues whose `updated` timestamp is unchanged should be skipped."""
    connector = _make_connector(tmp_path)
    issues = [_make_issue(key="PROJ-1", updated="2026-01-01T12:00:00.000+0000")]

    # Pre-populate state so the issue looks unchanged
    doc_id = str(uuid.uuid5(uuid.NAMESPACE_OID, "jira_issue:PROJ-1"))
    state: dict[str, _JiraIssueEntry] = {
        "PROJ-1": {"doc_id": doc_id, "updated": "2026-01-01T12:00:00.000+0000"}
    }
    await connector._save_issue_state(state)

    search_response = _make_search_response(issues)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = search_response
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("nexuspkm.connectors.jira.connector.httpx.AsyncClient", return_value=mock_client):
        docs = [doc async for doc in connector.fetch(since=None)]

    assert len(docs) == 0


async def test_incremental_yields_changed_issue(tmp_path: Path) -> None:
    """Issues with a new `updated` timestamp should be yielded."""
    connector = _make_connector(tmp_path)
    issues = [_make_issue(key="PROJ-1", updated="2026-01-02T12:00:00.000+0000")]

    doc_id = str(uuid.uuid5(uuid.NAMESPACE_OID, "jira_issue:PROJ-1"))
    state: dict[str, _JiraIssueEntry] = {
        "PROJ-1": {"doc_id": doc_id, "updated": "2026-01-01T12:00:00.000+0000"}
    }
    await connector._save_issue_state(state)

    search_response = _make_search_response(issues)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = search_response
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("nexuspkm.connectors.jira.connector.httpx.AsyncClient", return_value=mock_client):
        docs = [doc async for doc in connector.fetch(since=None)]

    assert len(docs) == 1
    assert docs[0].metadata.source_id == "PROJ-1"


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


async def test_pagination_fetches_all_pages(tmp_path: Path) -> None:
    """Connector should page through results until all issues are fetched."""
    connector = _make_connector(tmp_path)

    page1 = _make_search_response(
        [_make_issue(key=f"PROJ-{i}") for i in range(3)],
        total=5,
        start_at=0,
    )
    page2 = _make_search_response(
        [_make_issue(key=f"PROJ-{i}") for i in range(3, 5)],
        total=5,
        start_at=3,
    )

    call_count = 0

    async def _mock_get(url: str, **kwargs: object) -> MagicMock:
        nonlocal call_count
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = page1 if call_count == 0 else page2
        call_count += 1
        return resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = _mock_get

    with patch("nexuspkm.connectors.jira.connector.httpx.AsyncClient", return_value=mock_client):
        docs = [doc async for doc in connector.fetch(since=None)]

    assert len(docs) == 5
    assert call_count == 2


# ---------------------------------------------------------------------------
# fetch_deleted_ids
# ---------------------------------------------------------------------------


async def test_fetch_deleted_ids_returns_404_issues(tmp_path: Path) -> None:
    """Issues that return 404 should be reported as deleted."""
    connector = _make_connector(tmp_path)

    doc_id_1 = str(uuid.uuid5(uuid.NAMESPACE_OID, "jira_issue:PROJ-1"))
    doc_id_2 = str(uuid.uuid5(uuid.NAMESPACE_OID, "jira_issue:PROJ-2"))
    state: dict[str, _JiraIssueEntry] = {
        "PROJ-1": {"doc_id": doc_id_1, "updated": "2026-01-01T00:00:00.000+0000"},
        "PROJ-2": {"doc_id": doc_id_2, "updated": "2026-01-01T00:00:00.000+0000"},
    }
    await connector._save_issue_state(state)

    async def _mock_get(url: str, **kwargs: object) -> MagicMock:
        resp = MagicMock()
        if "PROJ-1" in url:
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
        else:
            resp.status_code = 404
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Not Found", request=MagicMock(), response=resp
            )
        return resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = _mock_get

    with patch("nexuspkm.connectors.jira.connector.httpx.AsyncClient", return_value=mock_client):
        deleted = await connector.fetch_deleted_ids(since=None)

    assert doc_id_2 in deleted
    assert doc_id_1 not in deleted


async def test_fetch_deleted_ids_empty_state(tmp_path: Path) -> None:
    """Empty state returns empty list without making HTTP calls."""
    connector = _make_connector(tmp_path)
    deleted = await connector.fetch_deleted_ids(since=None)
    assert deleted == []


# ---------------------------------------------------------------------------
# authenticate
# ---------------------------------------------------------------------------


async def test_authenticate_success(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("nexuspkm.connectors.jira.connector.httpx.AsyncClient", return_value=mock_client):
        result = await connector.authenticate()

    assert result is True


async def test_authenticate_failure(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("unauthorized"))

    with patch("nexuspkm.connectors.jira.connector.httpx.AsyncClient", return_value=mock_client):
        result = await connector.authenticate()

    assert result is False


# ---------------------------------------------------------------------------
# Missing env vars
# ---------------------------------------------------------------------------


def test_missing_env_vars_raises(tmp_path: Path) -> None:
    config = JiraConnectorConfig(enabled=True, base_url="https://example.atlassian.net")
    with patch.dict("os.environ", {}, clear=True), pytest.raises(OSError, match="JIRA_EMAIL"):
        JiraConnector(state_dir=tmp_path / "state", config=config)


# ---------------------------------------------------------------------------
# Sync state persistence
# ---------------------------------------------------------------------------


async def test_get_sync_state_empty(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    state = await connector.get_sync_state()
    assert state.last_synced_at is None


async def test_restore_and_get_sync_state(tmp_path: Path) -> None:
    from nexuspkm.models.document import SyncState

    connector = _make_connector(tmp_path)
    now = datetime.datetime.now(tz=datetime.UTC)
    state = SyncState(last_synced_at=now, documents_synced=5)
    await connector.restore_sync_state(state)
    loaded = await connector.get_sync_state()
    assert loaded.documents_synced == 5


# ---------------------------------------------------------------------------
# Rate limit retry cap
# ---------------------------------------------------------------------------


async def test_rate_limit_retries_exhausted(tmp_path: Path) -> None:
    """After _MAX_RATE_LIMIT_RETRIES (5) consecutive 429s the fetch aborts."""
    connector = _make_connector(tmp_path)

    async def _always_429(url: str, **kwargs: object) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 429
        resp.headers = {"Retry-After": "0"}
        resp.raise_for_status = MagicMock()
        return resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = _always_429

    with patch("nexuspkm.connectors.jira.connector.httpx.AsyncClient", return_value=mock_client):
        docs = [doc async for doc in connector.fetch(since=None)]

    assert docs == []
    status = await connector.health_check()
    assert status.status == "degraded"
    assert any("rate limit" in e for e in status.sync_errors)


async def test_rate_limit_counter_resets_after_success(tmp_path: Path) -> None:
    """A successful response resets the retry counter so later 429s don't compound."""
    connector = _make_connector(tmp_path)

    call_seq = iter(
        [429, 200, 200]  # one 429, then a normal page with 0 issues
    )

    async def _seq_responses(url: str, **kwargs: object) -> MagicMock:
        status = next(call_seq)
        resp = MagicMock()
        resp.status_code = status
        resp.headers = {"Retry-After": "0"}
        resp.raise_for_status = MagicMock()
        if status == 200:
            resp.json.return_value = {"issues": [], "total": 0, "startAt": 0}
        return resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = _seq_responses

    with patch("nexuspkm.connectors.jira.connector.httpx.AsyncClient", return_value=mock_client):
        docs = [doc async for doc in connector.fetch(since=None)]

    # Should complete cleanly with 0 docs (not abort due to the single 429)
    assert docs == []
    status = await connector.health_check()
    assert status.status == "healthy"
