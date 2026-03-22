"""Schedule & Task Management service.

Implements priority scoring, daily digest generation, team workload
calculation, and overlap detection. All graph queries are synchronous
(Kuzu) and wrapped with run_in_executor at the API layer.

Spec: F-012
NXP-86
"""

from __future__ import annotations

import asyncio
import math
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

import structlog

from nexuspkm.engine.graph_store import GraphStore
from nexuspkm.models.schedule import (
    ContextItem,
    DailyDigest,
    MeetingPrep,
    MeetingSummary,
    MemberWorkload,
    OverlapAlert,
    PersonSummary,
    PrioritizedItem,
    TeamWorkload,
)

log = structlog.get_logger(__name__)

# Number of days used as the exponential decay constant for urgency.
_URGENCY_DECAY_DAYS: float = 7.0

# Max relationship count assumed for importance normalisation.
_MAX_REL_COUNT: int = 20

# Workload score coefficients.
_WORKLOAD_ACTION_ITEM_WEIGHT: float = 10.0
_WORKLOAD_MEETING_WEIGHT: float = 5.0

# Top N action items surfaced per team member.
_TOP_ITEMS_PER_MEMBER: int = 3


class ScheduleService:
    """Business logic for schedule and task management analytics."""

    def __init__(self, graph_store: GraphStore) -> None:
        self._graph = graph_store

    # ------------------------------------------------------------------
    # Public async API (called by FastAPI handlers)
    # ------------------------------------------------------------------

    async def get_daily_digest(self, for_date: date | None = None) -> DailyDigest:
        loop = asyncio.get_running_loop()
        target = for_date or date.today()
        try:
            return await loop.run_in_executor(None, self._build_digest_sync, target)
        except Exception:
            log.exception("schedule.digest_error", date=str(target))
            raise

    async def get_prioritized_action_items(self) -> list[PrioritizedItem]:
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._build_prioritized_items_sync)
        except Exception:
            log.exception("schedule.action_items_error")
            raise

    async def get_team_workload(self) -> TeamWorkload:
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._build_team_workload_sync)
        except Exception:
            log.exception("schedule.team_workload_error")
            raise

    async def get_overlaps(self) -> list[OverlapAlert]:
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._detect_overlaps_sync)
        except Exception:
            log.exception("schedule.overlaps_error")
            raise

    # ------------------------------------------------------------------
    # Scoring helpers (internal but public for direct unit testing)
    # ------------------------------------------------------------------

    def _calculate_urgency(self, due_date: datetime | None) -> float:
        """Return 0-1 urgency based on how close the deadline is.

        - No due date  → 0.0
        - Overdue      → 1.0
        - Future       → exponential growth as deadline approaches
        """
        if due_date is None:
            return 0.0
        now = datetime.now(tz=UTC)
        # Ensure due_date is tz-aware for comparison
        if due_date.tzinfo is None:
            due_date = due_date.replace(tzinfo=UTC)
        days_remaining = (due_date - now).total_seconds() / 86400.0
        if days_remaining <= 0:
            return 1.0
        return math.exp(-days_remaining / _URGENCY_DECAY_DAYS)

    def _calculate_explicit_priority(self, status: str) -> float:
        """Return 0-1 explicit priority from the item's status/priority field."""
        if status == "high":
            return 1.0
        if status == "medium":
            return 0.5
        return 0.0

    def _calculate_importance(self, rel_count: int, max_count: int = _MAX_REL_COUNT) -> float:
        """Return 0-1 importance from graph relationship count."""
        if max_count <= 0:
            return 0.0
        return min(1.0, rel_count / max_count)

    def _combine_priority(self, urgency: float, importance: float, explicit: float) -> float:
        """Combine urgency, importance, and explicit priority into a 0-100 score."""
        raw = (urgency * 0.4) + (importance * 0.35) + (explicit * 0.25)
        return min(100.0, raw * 100.0)

    def _workload_status(self, score: float) -> str:
        """Map a 0-100 workload score to a status label."""
        if score < 30.0:
            return "light"
        if score <= 60.0:
            return "balanced"
        if score <= 80.0:
            return "heavy"
        return "overloaded"

    # ------------------------------------------------------------------
    # Sync graph-query methods (wrapped by async API above)
    # ------------------------------------------------------------------

    def _build_prioritized_items_sync(self) -> list[PrioritizedItem]:
        """Query open ActionItems and return them sorted by priority score."""
        rows = self._graph.execute(
            "MATCH (a:ActionItem) "
            "WHERE a.status = 'open' "
            "OPTIONAL MATCH (a)-[r]-() "
            "RETURN a.id AS id, a.description AS description, "
            "       a.status AS status, a.due_date AS due_date, "
            "       count(r) AS rel_count"
        )
        if not rows:
            return []

        # Normalise rel_count across this result set
        max_count = max((int(row.get("rel_count") or 0) for row in rows), default=0)
        max_count = max(max_count, _MAX_REL_COUNT)

        items: list[PrioritizedItem] = []
        for row in rows:
            due_date: datetime | None = row.get("due_date")
            status: str = row.get("status") or "open"
            rel_count: int = int(row.get("rel_count") or 0)

            urgency = self._calculate_urgency(due_date)
            importance = self._calculate_importance(rel_count, max_count)
            explicit = self._calculate_explicit_priority(status)
            score = self._combine_priority(urgency, importance, explicit)

            factors = self._build_factors(urgency, importance, explicit)
            items.append(
                PrioritizedItem(
                    entity_id=row["id"],
                    entity_type="ActionItem",
                    title=row.get("description") or "",
                    priority_score=round(score, 2),
                    urgency=round(urgency, 4),
                    importance=round(importance, 4),
                    factors=factors,
                )
            )

        return sorted(items, key=lambda x: x.priority_score, reverse=True)

    def _build_team_workload_sync(self) -> TeamWorkload:
        """Calculate per-person workload from the graph."""
        now = datetime.now(tz=UTC)

        # Fetch all persons
        person_rows = self._graph.execute(
            "MATCH (p:Person) RETURN p.id AS id, p.name AS name, p.email AS email"
        )

        # Single query: open action items with assignee, ordered for deterministic top-items.
        # Returns one row per (action_item, person) pair so we get both count and item IDs.
        assigned_rows = self._graph.execute(
            "MATCH (a:ActionItem)-[:ASSIGNED_TO]->(p:Person) "
            "WHERE a.status = 'open' "
            "RETURN a.id AS action_id, p.id AS person_id"
        )
        items_by_person: dict[str, list[str]] = defaultdict(list)
        ai_by_person: dict[str, int] = defaultdict(int)
        for r in assigned_rows:
            pid = r["person_id"]
            items_by_person[pid].append(r["action_id"])
            ai_by_person[pid] += 1

        # Count meetings this week per person (single now reference)
        week_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
            days=now.weekday()
        )
        week_end = week_start + timedelta(days=7)
        meeting_rows = self._graph.execute(
            "MATCH (p:Person)-[:ATTENDED]->(m:Meeting) "
            "WHERE m.date >= $week_start AND m.date < $week_end "
            "RETURN p.id AS person_id, count(m) AS meeting_count",
            {"week_start": week_start, "week_end": week_end},
        )
        meetings_by_person: dict[str, int] = {
            r["person_id"]: int(r["meeting_count"]) for r in meeting_rows
        }

        all_items = self._build_prioritized_items_sync()
        items_index: dict[str, PrioritizedItem] = {i.entity_id: i for i in all_items}

        members: list[MemberWorkload] = []
        for row in person_rows:
            pid = row["id"]
            open_count = ai_by_person.get(pid, 0)
            meeting_count = meetings_by_person.get(pid, 0)
            raw_score = (
                open_count * _WORKLOAD_ACTION_ITEM_WEIGHT + meeting_count * _WORKLOAD_MEETING_WEIGHT
            )
            score = min(100.0, raw_score)
            # Sort top items by descending priority score for the member's assigned items
            top_ids = items_by_person.get(pid, [])
            top_items = sorted(
                (items_index[aid] for aid in top_ids if aid in items_index),
                key=lambda x: x.priority_score,
                reverse=True,
            )[:_TOP_ITEMS_PER_MEMBER]

            members.append(
                MemberWorkload(
                    person=PersonSummary(
                        id=pid,
                        name=row.get("name") or "",
                        email=row.get("email") or "",
                    ),
                    open_action_items=open_count,
                    total_story_points=0,
                    meetings_this_week=meeting_count,
                    workload_score=round(score, 2),
                    status=self._workload_status(score),
                    top_items=top_items,
                )
            )

        overlaps = self._detect_overlaps_sync()
        return TeamWorkload(members=members, overlap_alerts=overlaps)

    def _detect_overlaps_sync(self) -> list[OverlapAlert]:
        """Find topics where multiple people have open action items."""
        rows = self._graph.execute(
            "MATCH (a:ActionItem)-[:ASSIGNED_TO]->(p:Person), "
            "      (d:Document)-[:TAGGED_WITH]->(t:Topic), "
            "      (p)-[:MENTIONED_IN]->(d) "
            "WHERE a.status = 'open' "
            "RETURN t.id AS topic_id, t.name AS topic_name, p.name AS person_name"
        )

        # Group persons by topic
        topic_names: dict[str, str] = {}
        persons_by_topic: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            tid = row["topic_id"]
            topic_names[tid] = row["topic_name"]
            persons_by_topic[tid].add(row["person_name"])

        alerts: list[OverlapAlert] = []
        for tid, persons in persons_by_topic.items():
            if len(persons) < 2:
                continue
            topic_name = topic_names[tid]
            people = sorted(persons)
            alerts.append(
                OverlapAlert(
                    topic=topic_name,
                    people_involved=people,
                    evidence=[],
                    description=(
                        f"{', '.join(people)} have open action items on topic '{topic_name}'"
                    ),
                )
            )

        return alerts

    def _build_digest_sync(self, for_date: date) -> DailyDigest:
        """Assemble a daily digest for the given date."""
        now = datetime.now(tz=UTC)
        day_start = datetime(for_date.year, for_date.month, for_date.day, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)

        # Upcoming meetings today
        meeting_rows = self._graph.execute(
            "MATCH (m:Meeting) "
            "WHERE m.date >= $start AND m.date < $end "
            "RETURN m.id AS id, m.title AS title, m.date AS date, "
            "       m.duration_minutes AS duration_minutes",
            {"start": day_start, "end": day_end},
        )

        all_items = self._build_prioritized_items_sync()
        overdue = [i for i in all_items if i.urgency >= 1.0]
        open_items = [i for i in all_items if i.urgency < 1.0]

        meeting_preps: list[MeetingPrep] = []
        for row in meeting_rows:
            m_date: datetime | None = row.get("date")
            if m_date is not None and m_date.tzinfo is None:
                m_date = m_date.replace(tzinfo=UTC)
            summary = MeetingSummary(
                id=row["id"],
                title=row.get("title") or "",
                date=m_date,
                duration_minutes=int(row.get("duration_minutes") or 0),
            )
            context = self._get_meeting_context_sync(row["id"])
            meeting_preps.append(
                MeetingPrep(
                    meeting=summary,
                    relevant_context=context,
                    suggested_talking_points=[],
                    action_items_to_follow_up=[],
                )
            )

        log.info(
            "schedule.digest_built",
            date=str(for_date),
            meetings=len(meeting_preps),
            open_items=len(open_items),
            overdue=len(overdue),
        )
        return DailyDigest(
            date=for_date,
            upcoming_meetings=meeting_preps,
            action_items=open_items,
            overdue_items=overdue,
            new_insights=[],
            generated_at=now,
        )

    def _get_meeting_context_sync(self, meeting_id: str) -> list[ContextItem]:
        """Return related context items for a meeting (docs from attendees)."""
        rows = self._graph.execute(
            "MATCH (p:Person)-[:ATTENDED]->(m:Meeting {id: $mid}), "
            "      (p)-[:MENTIONED_IN]->(d:Document) "
            "RETURN DISTINCT d.id AS doc_id, d.title AS title, d.source_type AS source_type",
            {"mid": meeting_id},
        )
        return [
            ContextItem(
                source_id=r["doc_id"],
                source_type=r.get("source_type") or "document",
                title=r.get("title") or "",
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_factors(
        self,
        urgency: float,
        importance: float,
        explicit: float,
    ) -> list[str]:
        factors: list[str] = []
        if urgency >= 1.0:
            factors.append("overdue")
        elif urgency > 0.5:
            factors.append("due soon")
        if importance > 0.5:
            factors.append("high connectivity")
        if explicit >= 1.0:
            factors.append("high priority")
        elif explicit >= 0.5:
            factors.append("medium priority")
        return factors
