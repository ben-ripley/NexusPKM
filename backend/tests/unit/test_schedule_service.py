"""Unit tests for schedule service business logic.

Tests priority scoring, workload calculation, overlap detection,
digest assembly, and team workload calculation.
Spec: F-012
NXP-86
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from nexuspkm.engine.graph_store import GraphStore
from nexuspkm.services.schedule import ScheduleService


@pytest.fixture
def mock_graph_store() -> MagicMock:
    return MagicMock(spec=GraphStore)


@pytest.fixture
def service(mock_graph_store: MagicMock) -> ScheduleService:
    return ScheduleService(mock_graph_store)


# ---------------------------------------------------------------------------
# Urgency calculation
# ---------------------------------------------------------------------------


def test_urgency_overdue_returns_1(service: ScheduleService) -> None:
    past = datetime.now(tz=UTC) - timedelta(days=1)
    assert service._calculate_urgency(past) == 1.0


def test_urgency_future_returns_between_0_and_1(service: ScheduleService) -> None:
    future = datetime.now(tz=UTC) + timedelta(days=7)
    urgency = service._calculate_urgency(future)
    assert 0.0 < urgency < 1.0


def test_urgency_no_due_date_returns_0(service: ScheduleService) -> None:
    assert service._calculate_urgency(None) == 0.0


def test_urgency_far_future_is_low(service: ScheduleService) -> None:
    far_future = datetime.now(tz=UTC) + timedelta(days=90)
    urgency = service._calculate_urgency(far_future)
    assert urgency < 0.1


def test_urgency_near_future_is_higher_than_far(service: ScheduleService) -> None:
    near = datetime.now(tz=UTC) + timedelta(days=1)
    far = datetime.now(tz=UTC) + timedelta(days=14)
    assert service._calculate_urgency(near) > service._calculate_urgency(far)


# ---------------------------------------------------------------------------
# Explicit priority
# ---------------------------------------------------------------------------


def test_explicit_priority_high(service: ScheduleService) -> None:
    assert service._calculate_explicit_priority("high") == 1.0


def test_explicit_priority_medium(service: ScheduleService) -> None:
    assert service._calculate_explicit_priority("medium") == 0.5


def test_explicit_priority_other(service: ScheduleService) -> None:
    assert service._calculate_explicit_priority("open") == 0.0
    assert service._calculate_explicit_priority("low") == 0.0
    assert service._calculate_explicit_priority("") == 0.0


# ---------------------------------------------------------------------------
# Priority score formula
# ---------------------------------------------------------------------------


def test_priority_score_formula(service: ScheduleService) -> None:
    # score = (urgency * 0.4 + importance * 0.35 + explicit * 0.25) * 100
    score = service._combine_priority(urgency=1.0, importance=1.0, explicit=1.0)
    assert math.isclose(score, 100.0, rel_tol=1e-6)


def test_priority_score_zero_components(service: ScheduleService) -> None:
    score = service._combine_priority(urgency=0.0, importance=0.0, explicit=0.0)
    assert math.isclose(score, 0.0, rel_tol=1e-6)


def test_priority_score_partial(service: ScheduleService) -> None:
    # urgency=0.5 → contributes 0.5*0.4=0.2; score = 0.2 * 100 = 20
    score = service._combine_priority(urgency=0.5, importance=0.0, explicit=0.0)
    assert math.isclose(score, 20.0, rel_tol=1e-6)


def test_priority_score_clamped_to_100(service: ScheduleService) -> None:
    score = service._combine_priority(urgency=2.0, importance=2.0, explicit=2.0)
    assert score <= 100.0


# ---------------------------------------------------------------------------
# Workload status thresholds
# ---------------------------------------------------------------------------


def test_workload_status_light(service: ScheduleService) -> None:
    assert service._workload_status(0.0) == "light"
    assert service._workload_status(29.9) == "light"


def test_workload_status_balanced(service: ScheduleService) -> None:
    assert service._workload_status(30.0) == "balanced"
    assert service._workload_status(60.0) == "balanced"


def test_workload_status_heavy(service: ScheduleService) -> None:
    assert service._workload_status(60.1) == "heavy"
    assert service._workload_status(80.0) == "heavy"


def test_workload_status_overloaded(service: ScheduleService) -> None:
    assert service._workload_status(80.1) == "overloaded"
    assert service._workload_status(100.0) == "overloaded"


# ---------------------------------------------------------------------------
# Overlap detection
# ---------------------------------------------------------------------------


def test_overlap_detection_alerts(service: ScheduleService, mock_graph_store: MagicMock) -> None:
    """Multiple persons with open ActionItems on the same topic → alert."""
    mock_graph_store.execute.return_value = [
        {"topic_id": "topic-1", "topic_name": "AI Migration", "person_name": "Alice"},
        {"topic_id": "topic-1", "topic_name": "AI Migration", "person_name": "Bob"},
    ]
    alerts = service._detect_overlaps_sync()
    assert len(alerts) == 1
    assert alerts[0].topic == "AI Migration"
    assert "Alice" in alerts[0].people_involved
    assert "Bob" in alerts[0].people_involved


def test_overlap_no_alert_single_person(
    service: ScheduleService, mock_graph_store: MagicMock
) -> None:
    """Single person on a topic → no alert."""
    mock_graph_store.execute.return_value = [
        {"topic_id": "topic-1", "topic_name": "AI Migration", "person_name": "Alice"},
    ]
    alerts = service._detect_overlaps_sync()
    assert len(alerts) == 0


def test_overlap_no_alert_empty_graph(
    service: ScheduleService, mock_graph_store: MagicMock
) -> None:
    mock_graph_store.execute.return_value = []
    alerts = service._detect_overlaps_sync()
    assert len(alerts) == 0


# ---------------------------------------------------------------------------
# Build prioritized items
# ---------------------------------------------------------------------------


def test_build_prioritized_items_empty_graph(
    service: ScheduleService, mock_graph_store: MagicMock
) -> None:
    mock_graph_store.execute.return_value = []
    items = service._build_prioritized_items_sync()
    assert items == []


def test_build_prioritized_items_returns_action_item(
    service: ScheduleService, mock_graph_store: MagicMock
) -> None:
    future = datetime.now(tz=UTC) + timedelta(days=7)
    mock_graph_store.execute.return_value = [
        {
            "id": "ai-1",
            "description": "Write tests",
            "status": "open",
            "due_date": future,
            "rel_count": 2,
        },
    ]
    items = service._build_prioritized_items_sync()
    assert len(items) == 1
    assert items[0].entity_id == "ai-1"
    assert items[0].entity_type == "ActionItem"
    assert 0.0 <= items[0].priority_score <= 100.0


def test_build_prioritized_items_sorted_descending(
    service: ScheduleService, mock_graph_store: MagicMock
) -> None:
    now = datetime.now(tz=UTC)
    near = now + timedelta(days=1)
    far = now + timedelta(days=30)
    mock_graph_store.execute.return_value = [
        {
            "id": "ai-far",
            "description": "Low urgency",
            "status": "open",
            "due_date": far,
            "rel_count": 0,
        },
        {
            "id": "ai-near",
            "description": "High urgency",
            "status": "open",
            "due_date": near,
            "rel_count": 0,
        },
    ]
    items = service._build_prioritized_items_sync()
    assert items[0].priority_score >= items[1].priority_score


# ---------------------------------------------------------------------------
# _get_meeting_context_sync
# ---------------------------------------------------------------------------


def test_get_meeting_context_returns_context_items(
    service: ScheduleService, mock_graph_store: MagicMock
) -> None:
    mock_graph_store.execute.return_value = [
        {"doc_id": "d-1", "title": "Project Notes", "source_type": "obsidian"},
    ]
    context = service._get_meeting_context_sync("m-1")
    assert len(context) == 1
    assert context[0].source_id == "d-1"
    assert context[0].title == "Project Notes"
    assert context[0].source_type == "obsidian"


def test_get_meeting_context_empty(service: ScheduleService, mock_graph_store: MagicMock) -> None:
    mock_graph_store.execute.return_value = []
    context = service._get_meeting_context_sync("m-no-attendees")
    assert context == []


# ---------------------------------------------------------------------------
# _build_digest_sync
# ---------------------------------------------------------------------------


def test_build_digest_no_meetings(service: ScheduleService, mock_graph_store: MagicMock) -> None:
    """Digest with no meetings or items has empty lists."""
    # call order: meetings query → action items query
    mock_graph_store.execute.side_effect = [
        [],  # meetings for the day
        [],  # action items (_build_prioritized_items_sync)
    ]
    target = date(2026, 3, 21)
    digest = service._build_digest_sync(target)
    assert digest.date == target
    assert digest.upcoming_meetings == []
    assert digest.action_items == []
    assert digest.overdue_items == []
    assert isinstance(digest.generated_at, datetime)


def test_build_digest_includes_meeting(
    service: ScheduleService, mock_graph_store: MagicMock
) -> None:
    """Meetings on the target date are included in upcoming_meetings."""
    meeting_dt = datetime(2026, 3, 21, 10, 0, tzinfo=UTC)
    # call order: meetings query → action items query → context query for m-1
    mock_graph_store.execute.side_effect = [
        [{"id": "m-1", "title": "Standup", "date": meeting_dt, "duration_minutes": 30}],
        [],  # action items
        [],  # context for m-1
    ]
    digest = service._build_digest_sync(date(2026, 3, 21))
    assert len(digest.upcoming_meetings) == 1
    assert digest.upcoming_meetings[0].meeting.id == "m-1"
    assert digest.upcoming_meetings[0].meeting.title == "Standup"


def test_build_digest_separates_overdue_from_open(
    service: ScheduleService, mock_graph_store: MagicMock
) -> None:
    """Overdue items (urgency=1.0) are separated from open items."""
    past = datetime.now(tz=UTC) - timedelta(days=2)
    future = datetime.now(tz=UTC) + timedelta(days=7)
    mock_graph_store.execute.side_effect = [
        [],  # no meetings
        [
            {
                "id": "ai-overdue",
                "description": "Late task",
                "status": "open",
                "due_date": past,
                "rel_count": 0,
            },
            {
                "id": "ai-open",
                "description": "Future task",
                "status": "open",
                "due_date": future,
                "rel_count": 0,
            },
        ],
    ]
    digest = service._build_digest_sync(date.today())
    assert len(digest.overdue_items) == 1
    assert digest.overdue_items[0].entity_id == "ai-overdue"
    assert len(digest.action_items) == 1
    assert digest.action_items[0].entity_id == "ai-open"


# ---------------------------------------------------------------------------
# _build_team_workload_sync
# ---------------------------------------------------------------------------


def test_build_team_workload_returns_members(
    service: ScheduleService, mock_graph_store: MagicMock
) -> None:
    """All persons from the graph appear as members."""
    # call order: persons → assigned rows → meetings → action items → overlaps
    mock_graph_store.execute.side_effect = [
        [{"id": "p-1", "name": "Alice", "email": "alice@example.com"}],
        [],  # no assigned action items
        [],  # no meetings this week
        [],  # action items (prioritized)
        [],  # overlaps
    ]
    workload = service._build_team_workload_sync()
    assert len(workload.members) == 1
    assert workload.members[0].person.name == "Alice"
    assert workload.members[0].open_action_items == 0
    assert workload.members[0].meetings_this_week == 0
    assert workload.members[0].workload_score == 0.0
    assert workload.members[0].status == "light"


def test_build_team_workload_score_calculation(
    service: ScheduleService, mock_graph_store: MagicMock
) -> None:
    """Workload score = open_items*10 + meetings*5."""
    mock_graph_store.execute.side_effect = [
        [{"id": "p-1", "name": "Bob", "email": ""}],
        # 2 action items assigned to p-1
        [{"action_id": "ai-1", "person_id": "p-1"}, {"action_id": "ai-2", "person_id": "p-1"}],
        # 3 meetings this week
        [{"person_id": "p-1", "meeting_count": 3}],
        [],  # action items (prioritized items list empty)
        [],  # overlaps
    ]
    workload = service._build_team_workload_sync()
    member = workload.members[0]
    assert member.open_action_items == 2
    assert member.meetings_this_week == 3
    # 2*10 + 3*5 = 35
    assert member.workload_score == 35.0
    assert member.status == "balanced"


def test_build_team_workload_overloaded_threshold(
    service: ScheduleService, mock_graph_store: MagicMock
) -> None:
    """10 open items alone → workload_score=100, status=overloaded."""
    mock_graph_store.execute.side_effect = [
        [{"id": "p-1", "name": "Charlie", "email": ""}],
        [{"action_id": f"ai-{i}", "person_id": "p-1"} for i in range(10)],
        [],  # no meetings
        [],  # prioritized items
        [],  # overlaps
    ]
    workload = service._build_team_workload_sync()
    member = workload.members[0]
    assert member.workload_score == 100.0
    assert member.status == "overloaded"


def test_build_team_workload_empty_graph(
    service: ScheduleService, mock_graph_store: MagicMock
) -> None:
    """Empty graph → empty members list."""
    mock_graph_store.execute.side_effect = [
        [],  # no persons
        [],  # assigned rows
        [],  # meetings
        [],  # action items
        [],  # overlaps
    ]
    workload = service._build_team_workload_sync()
    assert workload.members == []
    assert workload.overlap_alerts == []
