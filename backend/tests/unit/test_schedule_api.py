"""Unit tests for schedule API endpoints.

Tests GET /api/schedule/digest, /api/schedule/action-items,
      /api/schedule/team-workload, /api/schedule/overlaps.
Spec: F-012
NXP-86
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from nexuspkm.api.schedule import get_schedule_service
from nexuspkm.main import app
from nexuspkm.models.schedule import (
    DailyDigest,
    MemberWorkload,
    OverlapAlert,
    PersonSummary,
    PrioritizedItem,
    TeamWorkload,
)
from nexuspkm.services.schedule import ScheduleService


def _make_mock_service() -> MagicMock:
    svc = MagicMock(spec=ScheduleService)

    svc.get_daily_digest = AsyncMock(
        return_value=DailyDigest(
            date=date.today(),
            upcoming_meetings=[],
            action_items=[],
            overdue_items=[],
            new_insights=[],
            generated_at=datetime.now(tz=UTC),
        )
    )

    svc.get_prioritized_action_items = AsyncMock(return_value=[])

    svc.get_team_workload = AsyncMock(return_value=TeamWorkload(members=[], overlap_alerts=[]))

    svc.get_overlaps = AsyncMock(return_value=[])

    return svc


@pytest.fixture
def mock_service() -> MagicMock:
    return _make_mock_service()


@pytest.fixture
def client(mock_service: MagicMock) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_schedule_service] = lambda: mock_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_schedule_service, None)


# ---------------------------------------------------------------------------
# GET /api/schedule/digest
# ---------------------------------------------------------------------------


def test_digest_returns_200(client: TestClient) -> None:
    response = client.get("/api/schedule/digest")
    assert response.status_code == 200
    data = response.json()
    assert "date" in data
    assert "upcoming_meetings" in data
    assert "action_items" in data
    assert "overdue_items" in data
    assert "new_insights" in data
    assert "generated_at" in data


def test_digest_with_date_param(client: TestClient, mock_service: MagicMock) -> None:
    response = client.get("/api/schedule/digest?for_date=2026-03-21")
    assert response.status_code == 200
    mock_service.get_daily_digest.assert_called_once_with(for_date=date(2026, 3, 21))


def test_digest_invalid_date_returns_422(client: TestClient) -> None:
    response = client.get("/api/schedule/digest?for_date=not-a-date")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/schedule/action-items
# ---------------------------------------------------------------------------


def test_action_items_returns_200(client: TestClient) -> None:
    response = client.get("/api/schedule/action-items")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_action_items_returns_sorted_list(client: TestClient, mock_service: MagicMock) -> None:
    item = PrioritizedItem(
        entity_id="ai-1",
        entity_type="ActionItem",
        title="Fix bug",
        priority_score=75.0,
        urgency=0.8,
        importance=0.5,
        factors=["overdue"],
    )
    mock_service.get_prioritized_action_items = AsyncMock(return_value=[item])
    response = client.get("/api/schedule/action-items")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["entity_id"] == "ai-1"
    assert data[0]["priority_score"] == 75.0


# ---------------------------------------------------------------------------
# GET /api/schedule/team-workload
# ---------------------------------------------------------------------------


def test_team_workload_returns_200(client: TestClient) -> None:
    response = client.get("/api/schedule/team-workload")
    assert response.status_code == 200
    data = response.json()
    assert "members" in data
    assert "overlap_alerts" in data


def test_team_workload_with_members(client: TestClient, mock_service: MagicMock) -> None:
    member = MemberWorkload(
        person=PersonSummary(id="p-1", name="Alice"),
        open_action_items=3,
        total_story_points=0,
        meetings_this_week=2,
        workload_score=35.0,
        status="balanced",
        top_items=[],
    )
    mock_service.get_team_workload = AsyncMock(
        return_value=TeamWorkload(members=[member], overlap_alerts=[])
    )
    response = client.get("/api/schedule/team-workload")
    assert response.status_code == 200
    data = response.json()
    assert len(data["members"]) == 1
    assert data["members"][0]["person"]["name"] == "Alice"


# ---------------------------------------------------------------------------
# GET /api/schedule/overlaps
# ---------------------------------------------------------------------------


def test_overlaps_returns_200(client: TestClient) -> None:
    response = client.get("/api/schedule/overlaps")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_overlaps_with_alerts(client: TestClient, mock_service: MagicMock) -> None:
    alert = OverlapAlert(
        topic="AI Migration",
        people_involved=["Alice", "Bob"],
        evidence=[],
        description="Both Alice and Bob have open action items on AI Migration",
    )
    mock_service.get_overlaps = AsyncMock(return_value=[alert])
    response = client.get("/api/schedule/overlaps")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["topic"] == "AI Migration"
    assert "Alice" in data[0]["people_involved"]


# ---------------------------------------------------------------------------
# 503 when service unavailable
# ---------------------------------------------------------------------------


def test_503_when_schedule_service_unavailable() -> None:
    # Ensure get_schedule_service raises 503 when not overridden
    app.dependency_overrides.pop(get_schedule_service, None)
    try:
        response = TestClient(app).get("/api/schedule/digest")
        assert response.status_code == 503
    finally:
        # No override was set, so nothing to restore
        pass
