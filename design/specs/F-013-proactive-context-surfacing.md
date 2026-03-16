# F-013: Proactive Context Surfacing

**Spec Version:** 1.0
**Date:** 2026-03-16
**Priority:** V3+

## Overview

Automatically surfaces relevant context without the user explicitly searching. Includes pre-meeting preparation, related content suggestions during note-taking, contradiction alerts, and a notification system for surfaced insights.

## User Stories

- As a user, I want to see relevant context automatically assembled before my meetings
- As a user, I want to be notified when new information connects to or contradicts existing knowledge
- As a user, I want the system to proactively show me related content when I'm working on a topic

## Functional Requirements

### FR-1: Pre-Meeting Context Assembly

Triggered by upcoming calendar events (scanned periodically):

```python
class MeetingContext(BaseModel):
    meeting_id: str
    meeting_title: str
    meeting_time: datetime
    attendees: list[PersonSummary]

    # Assembled context
    previous_meetings: list[DocumentSummary]  # Past meetings with same attendees/topic
    related_tickets: list[DocumentSummary]     # JIRA tickets connected to meeting topic
    related_notes: list[DocumentSummary]       # Obsidian notes on the topic
    related_emails: list[DocumentSummary]      # Email threads with same participants
    open_action_items: list[ActionItemSummary] # Pending items for attendees
    suggested_agenda: list[str]               # LLM-generated from context
```

Assembly process:
1. Extract entities from meeting title and description
2. Find attendees in the knowledge graph
3. Traverse graph: attendee → past meetings, related documents, action items
4. Topic matching: meeting title entities → related Topics → connected documents
5. LLM summarization: generate a concise briefing from gathered context
6. Timing: assemble 1 hour before meeting (configurable)

### FR-2: Related Content Suggestions

When a new document is ingested:
1. Extract entities from the new document
2. Query the graph for existing documents connected to the same entities
3. Calculate similarity scores
4. If strong connections found (score > threshold), generate a notification

```python
class RelatedContentAlert(BaseModel):
    new_document: DocumentSummary
    related_documents: list[DocumentSummary]
    connection_type: str        # "same_topic", "same_people", "same_project"
    connection_strength: float  # 0-1
    summary: str               # LLM-generated explanation of the connection
```

### FR-3: Contradiction Alerts

When entity extraction (F-006) detects contradictions:
1. Create a notification with both conflicting values and their sources
2. Severity: high (dates/deadlines), medium (status), low (descriptions)
3. User can dismiss, resolve (pick one), or flag for discussion

### FR-4: Notification System

```python
class Notification(BaseModel):
    id: str
    type: str                  # "meeting_prep", "related_content", "contradiction", "insight"
    title: str
    summary: str
    priority: str              # "high", "medium", "low"
    data: dict                 # Type-specific payload
    read: bool = False
    created_at: datetime

class NotificationPreferences(BaseModel):
    meeting_prep_enabled: bool = True
    meeting_prep_lead_time_minutes: int = 60
    related_content_enabled: bool = True
    related_content_threshold: float = 0.7
    contradiction_alerts_enabled: bool = True
```

- Notifications stored in SQLite
- Delivered via: in-app notification panel, WebSocket push to UI
- Configurable per notification type

### FR-5: Background Processing

- **Meeting scanner**: runs every 15 minutes, checks for upcoming meetings within the prep window
- **Connection scanner**: runs after each document ingestion
- **Contradiction scanner**: runs as part of entity extraction (F-006)
- All scanners run as async background tasks via APScheduler

### FR-6: Extensibility Point

- Notifications can trigger external actions via webhook
- Configurable webhook URL per notification type
- Payload format: JSON with notification data
- This is the integration point for future workflow automation (n8n, etc.)

## Non-Functional Requirements

- Meeting prep assembly < 15 seconds per meeting
- Notifications delivered within 30 seconds of trigger event
- Background scanners must not impact chat or search performance
- Notification storage must support 10K+ notifications

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/notifications` | List notifications (filterable, paginated) |
| GET | `/api/notifications/unread-count` | Unread notification count |
| PUT | `/api/notifications/{id}/read` | Mark notification as read |
| DELETE | `/api/notifications/{id}` | Dismiss notification |
| GET | `/api/context/meeting/{meeting_id}` | Get assembled meeting context |
| GET | `/api/context/preferences` | Get notification preferences |
| PUT | `/api/context/preferences` | Update notification preferences |

## UI/UX Requirements

- Notification bell in the top bar with unread count badge
- Notification dropdown panel showing recent notifications
- Meeting prep panel: expandable card with full context, suggested agenda, related docs
- Notification settings in the Settings page

## Testing Strategy

### Unit Tests
- Test meeting context assembly logic with mock graph data
- Test related content scoring
- Test notification creation and management
- Test preference filtering

### Integration Tests
- Test meeting scanner with populated calendar and knowledge graph
- Test connection scanner with new document ingestion
- Test notification WebSocket delivery

## Dependencies

- F-002 (Knowledge Engine Core) — for graph queries
- F-006 (Entity Extraction) — for contradiction detection
- F-010 (Outlook Connector) — for calendar data
- F-008 (Web Dashboard) — for notification UI integration

## Acceptance Criteria

- [ ] Meeting context is assembled automatically before scheduled meetings
- [ ] Related content alerts fire when new documents connect to existing knowledge
- [ ] Contradiction alerts surface conflicting information with source references
- [ ] Notifications appear in-app with correct priority levels
- [ ] Notification preferences control which alerts are generated
- [ ] Webhook extensibility point sends notifications to configured URLs
- [ ] Background scanners run without impacting application performance
