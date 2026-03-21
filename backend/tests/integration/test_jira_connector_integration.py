"""Integration tests for JiraConnector.

Tests the full fetch flow with mocked JIRA API responses.
Spec: F-011
NXP-85
"""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from nexuspkm.config.models import JiraConnectorConfig
from nexuspkm.connectors.jira.connector import JiraConnector
from nexuspkm.models.document import SourceType

_BASE_URL = "https://example.atlassian.net"


def _make_connector(tmp_path: Path, **kwargs: object) -> JiraConnector:
    config = JiraConnectorConfig(
        enabled=True,
        base_url=_BASE_URL,
        **kwargs,  # type: ignore[arg-type]
    )
    with patch.dict("os.environ", {"JIRA_EMAIL": "user@example.com", "JIRA_API_TOKEN": "tok"}):
        return JiraConnector(state_dir=tmp_path / "state", config=config)


def _make_issue(
    key: str,
    summary: str = "A ticket",
    updated: str = "2026-01-01T12:00:00.000+0000",
    created: str = "2026-01-01T10:00:00.000+0000",
    comments: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "id": "10001",
        "key": key,
        "fields": {
            "summary": summary,
            "description": "Desc",
            "status": {"name": "Open"},
            "issuetype": {"name": "Task"},
            "priority": {"name": "Medium"},
            "reporter": {"displayName": "Alice"},
            "assignee": {"displayName": "Bob"},
            "labels": [],
            "components": [],
            "created": created,
            "updated": updated,
            "comment": {"comments": comments or []},
            "parent": None,
            "customfield_10016": None,
            "customfield_10020": None,
        },
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


def _mock_client_for(responses: list[dict[str, object]]) -> MagicMock:
    """Return a mock AsyncClient that returns each response in order on GET /search."""
    call_idx = 0

    async def _get(url: str, **kwargs: object) -> MagicMock:
        nonlocal call_idx
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = responses[min(call_idx, len(responses) - 1)]
        call_idx += 1
        return resp

    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    mock.get = _get
    return mock


# ---------------------------------------------------------------------------
# Full sync flow
# ---------------------------------------------------------------------------


async def test_full_sync_yields_all_issues(tmp_path: Path) -> None:
    """Full sync yields one Document per issue."""
    issues = [
        _make_issue("PROJ-1", summary="Issue One"),
        _make_issue("PROJ-2", summary="Issue Two"),
        _make_issue("PROJ-3", summary="Issue Three"),
    ]
    connector = _make_connector(tmp_path)
    response = _make_search_response(issues)
    mock_client = _mock_client_for([response])

    with patch("nexuspkm.connectors.jira.connector.httpx.AsyncClient", return_value=mock_client):
        docs = [doc async for doc in connector.fetch(since=None)]

    assert len(docs) == 3
    keys = {doc.metadata.source_id for doc in docs}
    assert keys == {"PROJ-1", "PROJ-2", "PROJ-3"}


async def test_full_sync_document_fields(tmp_path: Path) -> None:
    """Verify that Document fields are correctly populated."""
    comment = {
        "author": {"displayName": "Carol"},
        "body": "Great fix!",
        "created": "2026-01-02T08:00:00.000+0000",
    }
    issue = _make_issue("NXP-10", summary="Fix the bug", comments=[comment])
    connector = _make_connector(tmp_path)
    response = _make_search_response([issue])
    mock_client = _mock_client_for([response])

    with patch("nexuspkm.connectors.jira.connector.httpx.AsyncClient", return_value=mock_client):
        docs = [doc async for doc in connector.fetch(since=None)]

    assert len(docs) == 1
    doc = docs[0]
    assert doc.metadata.source_type == SourceType.JIRA_ISSUE
    assert doc.metadata.source_id == "NXP-10"
    assert doc.metadata.title == "NXP-10: Fix the bug"
    assert doc.metadata.author == "Alice"
    assert str(doc.metadata.url) == f"{_BASE_URL}/browse/NXP-10"
    assert "NXP-10: Fix the bug" in doc.content
    assert "Great fix!" in doc.content
    assert "[Carol - 2026-01-02]: Great fix!" in doc.content
    expected_id = str(uuid.uuid5(uuid.NAMESPACE_OID, "jira_issue:NXP-10"))
    assert doc.id == expected_id


async def test_sync_state_persisted_after_fetch(tmp_path: Path) -> None:
    """State file is written after a successful fetch."""
    issues = [_make_issue("PROJ-1")]
    connector = _make_connector(tmp_path)
    response = _make_search_response(issues)
    mock_client = _mock_client_for([response])

    with patch("nexuspkm.connectors.jira.connector.httpx.AsyncClient", return_value=mock_client):
        _ = [doc async for doc in connector.fetch(since=None)]

    state_file = tmp_path / "state" / "jira_sync_state.json"
    assert state_file.exists()
    import json

    state = json.loads(state_file.read_text())
    assert "PROJ-1" in state


async def test_pagination_full_flow(tmp_path: Path) -> None:
    """Two pages of results are fully consumed."""
    page1 = _make_search_response(
        [_make_issue(f"PROJ-{i}") for i in range(3)],
        total=5,
        start_at=0,
    )
    page2 = _make_search_response(
        [_make_issue(f"PROJ-{i}") for i in range(3, 5)],
        total=5,
        start_at=3,
    )
    connector = _make_connector(tmp_path)
    mock_client = _mock_client_for([page1, page2])

    with patch("nexuspkm.connectors.jira.connector.httpx.AsyncClient", return_value=mock_client):
        docs = [doc async for doc in connector.fetch(since=None)]

    assert len(docs) == 5


async def test_incremental_sync_with_since(tmp_path: Path) -> None:
    """JQL includes updated >= when `since` is provided."""
    connector = _make_connector(tmp_path, jql_filter="project = PROJ")
    response = _make_search_response([_make_issue("PROJ-1")])
    captured_params: list[dict[str, object]] = []

    async def _get(
        url: str, params: dict[str, object] | None = None, **kwargs: object
    ) -> MagicMock:
        if params:
            captured_params.append(dict(params))
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = response
        return resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = _get

    since = datetime.datetime(2026, 1, 15, 0, 0, 0, tzinfo=datetime.UTC)
    with patch("nexuspkm.connectors.jira.connector.httpx.AsyncClient", return_value=mock_client):
        _ = [doc async for doc in connector.fetch(since=since)]

    assert len(captured_params) == 1
    jql = captured_params[0]["jql"]
    assert "project = PROJ" in jql
    assert "updated >=" in jql
    assert "2026-01-15" in jql


async def test_http_error_recorded_in_health_check(tmp_path: Path) -> None:
    """HTTP errors during fetch are recorded and reflected in health_check."""
    connector = _make_connector(tmp_path)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    with patch("nexuspkm.connectors.jira.connector.httpx.AsyncClient", return_value=mock_client):
        _ = [doc async for doc in connector.fetch(since=None)]

    status = await connector.health_check()
    assert status.status == "degraded"
    assert len(status.sync_errors) > 0


async def test_empty_result_set(tmp_path: Path) -> None:
    """Zero issues → zero documents, no errors."""
    connector = _make_connector(tmp_path)
    response = _make_search_response([])
    mock_client = _mock_client_for([response])

    with patch("nexuspkm.connectors.jira.connector.httpx.AsyncClient", return_value=mock_client):
        docs = [doc async for doc in connector.fetch(since=None)]

    assert docs == []
    status = await connector.health_check()
    assert status.status == "healthy"
