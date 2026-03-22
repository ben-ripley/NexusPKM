"""Unit tests for schedule service business logic.

Tests priority scoring, workload calculation, and overlap detection.
Spec: F-012
NXP-86
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
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
