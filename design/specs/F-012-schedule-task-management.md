# F-012: Schedule & Task Management

**Spec Version:** 1.0
**Date:** 2026-03-16
**Priority:** V3+

## Overview

Derives schedule awareness and task priorities from ingested data. Provides daily digests, team workload visibility, and overlap/conflict detection. Read-only in v1 — surfaces recommendations that the user acts on manually.

## User Stories

- As a user, I want a daily digest of my upcoming meetings with relevant context from previous discussions
- As a user, I want to see my team's workload at a glance (who is overloaded, who has capacity)
- As a user, I want pending action items prioritized by urgency and importance
- As a user, I want to know when the same topic is being worked on by multiple people

## Functional Requirements

### FR-1: Priority Scoring

```python
class PrioritizedItem(BaseModel):
    entity_id: str
    entity_type: str          # ActionItem, Meeting
    title: str
    priority_score: float     # 0-100
    urgency: float            # Deadline proximity component
    importance: float         # Graph connectivity component
    factors: list[str]        # Human-readable priority factors

def calculate_priority(item, graph_context) -> float:
    urgency = deadline_urgency(item.due_date)      # 0-1, exponential as deadline approaches
    importance = graph_importance(item, graph_context)  # 0-1, based on entity connections
    explicit = explicit_priority(item)              # 0-1, from JIRA priority or manual tags

    return (urgency * 0.4) + (importance * 0.35) + (explicit * 0.25)
```

- **Urgency**: exponential growth as deadline approaches. Overdue items = maximum urgency.
- **Importance**: based on graph connectivity — items connected to more entities (people, projects) are more important
- **Explicit priority**: from source metadata (JIRA priority field, frontmatter tags)

### FR-2: Daily Digest

Generated on demand or on schedule:

```python
class DailyDigest(BaseModel):
    date: date
    upcoming_meetings: list[MeetingPrep]
    action_items: list[PrioritizedItem]
    overdue_items: list[PrioritizedItem]
    new_insights: list[str]       # Newly discovered relationships/contradictions
    generated_at: datetime

class MeetingPrep(BaseModel):
    meeting: MeetingSummary
    relevant_context: list[ContextItem]  # Previous discussions, related tickets, notes
    suggested_talking_points: list[str]
    action_items_to_follow_up: list[PrioritizedItem]
```

- Meeting prep: for each upcoming meeting, gather related documents from the knowledge graph (previous meetings with same participants, topics, related JIRA tickets)
- LLM-generated suggested talking points based on gathered context
- Action items sorted by priority score

### FR-3: Team Workload View

```python
class TeamWorkload(BaseModel):
    members: list[MemberWorkload]
    overlap_alerts: list[OverlapAlert]

class MemberWorkload(BaseModel):
    person: PersonSummary
    open_action_items: int
    total_story_points: int
    meetings_this_week: int
    workload_score: float         # 0-100, composite metric
    status: str                   # "balanced", "heavy", "light", "overloaded"
    top_items: list[PrioritizedItem]

class OverlapAlert(BaseModel):
    topic: str
    people_involved: list[str]
    evidence: list[str]           # Source references
    description: str
```

- Workload score combines: open items, story points, meeting load
- Thresholds: light (< 30), balanced (30-60), heavy (60-80), overloaded (> 80)
- Overlap detection: use knowledge graph to find when multiple people are connected to the same Topic/Project with similar action items

### FR-4: Overlap & Conflict Detection

- **Topic overlap**: same Topic entity connected to multiple Person entities with active ActionItems
- **Schedule conflict**: overlapping calendar events (if calendar data available)
- **Information conflict**: contradictions detected by F-006 that affect scheduling decisions
- Run as a background job after each sync cycle
- Surface as alerts in the dashboard and digest

## Non-Functional Requirements

- Daily digest generation < 30 seconds
- Workload calculations updated after each connector sync
- Priority scores recalculated when new data is ingested

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/schedule/digest` | Generate daily digest |
| GET | `/api/schedule/digest?date={date}` | Digest for a specific date |
| GET | `/api/schedule/action-items` | Prioritized action item list |
| GET | `/api/schedule/team-workload` | Team workload view |
| GET | `/api/schedule/overlaps` | Detected overlaps and conflicts |

## UI/UX Requirements

- Dashboard integration: upcoming meetings card, action items card
- Dedicated schedule view: calendar-style view with meeting prep panels
- Team workload dashboard: member cards with workload indicators, overlap alerts
- Action items list: sortable by priority, filterable by assignee/project

## Testing Strategy

### Unit Tests
- Test priority scoring with various urgency/importance/explicit values
- Test workload score calculation
- Test overlap detection logic
- Test digest assembly

### Integration Tests
- Test digest generation with populated knowledge base
- Test workload calculation with JIRA and calendar data
- Test overlap detection across multiple data sources

## Dependencies

- F-002 (Knowledge Engine Core) — for graph queries
- F-006 (Entity Extraction) — for Person, ActionItem, Topic entities
- F-010 (Outlook Connector) — for calendar data (optional)
- F-011 (JIRA Connector) — for workload data (optional)

## Acceptance Criteria

- [ ] Daily digest includes upcoming meetings with relevant context
- [ ] Action items are ranked by priority score
- [ ] Team workload view shows per-person workload metrics
- [ ] Overlap detection identifies when multiple people work on the same topic
- [ ] Digest generation completes in < 30 seconds
- [ ] System functions with partial data (e.g., no calendar connector)
