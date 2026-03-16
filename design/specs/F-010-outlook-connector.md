# F-010: Outlook Connector (Email & Calendar)

**Spec Version:** 1.0
**Date:** 2026-03-16
**ADR Reference:** ADR-004
**Priority:** V2

## Overview

Ingests emails and calendar events from Microsoft Outlook via the Microsoft Graph API. Shares the OAuth2 authentication module with the Teams connector. Supports incremental sync via delta queries for efficient ongoing synchronization.

## User Stories

- As a user, I want my emails searchable in my knowledge base so I can find information from past conversations
- As a user, I want my calendar events ingested so the system understands my schedule
- As a user, I want to filter which emails are ingested (e.g., specific folders, date ranges)
- As a user, I want email threads grouped together, not treated as individual documents

## Functional Requirements

### FR-1: Shared Microsoft Graph Authentication

Extends the OAuth2 module from F-003 with additional permissions:
- `Mail.Read` (delegated) — read email
- `Calendars.Read` (delegated) — read calendar events
- Token storage shared with Teams connector at `data/.tokens/ms_graph.json`

### FR-2: Email Ingestion

#### Discovery
```
GET /me/messages
  ?$filter=receivedDateTime ge {since_timestamp}
  &$select=id,subject,bodyPreview,body,from,toRecipients,ccRecipients,
           receivedDateTime,conversationId,hasAttachments,parentFolderId
  &$top=50
  &$orderby=receivedDateTime desc
```

Or via delta query for incremental sync:
```
GET /me/messages/delta
  ?$deltatoken={stored_delta_token}
```

#### Configurable Filters
```yaml
connectors:
  outlook_email:
    enabled: true
    settings:
      folders:
        - Inbox
        - "Project X"
      exclude_folders:
        - Junk Email
        - Deleted Items
      sender_domains:
        - company.com
      date_from: "2025-01-01"
      max_emails_per_sync: 500
```

#### Thread Grouping
- Group emails by `conversationId`
- Create a single Document per thread (concatenated, chronologically ordered)
- Thread title = subject of first email
- Thread participants = union of all senders/recipients
- Update thread Document when new emails arrive in the same conversation

#### Email Processing
- Extract plain text body (prefer text/plain, fall back to HTML → text conversion)
- Extract: subject, sender, recipients (to/cc), timestamps, conversation ID
- Attachment handling: extract text from .txt, .md, .csv attachments; skip binary files; note attachment names in metadata

### FR-3: Calendar Event Ingestion

```
GET /me/calendarView
  ?startDateTime={window_start}
  &endDateTime={window_end}
  &$select=id,subject,body,start,end,location,attendees,organizer,isOnlineMeeting,recurrence
  &$top=100
```

#### Event Processing
```python
Document(
    id=generate_uuid(),
    content=f"{subject}\n\n{body_text}\n\nAttendees: {attendee_list}\nLocation: {location}",
    metadata=DocumentMetadata(
        source_type=SourceType.OUTLOOK_CALENDAR,
        source_id=event_id,
        title=subject,
        participants=[a["emailAddress"]["name"] for a in attendees],
        created_at=start_datetime,
        updated_at=start_datetime,
        synced_at=datetime.utcnow(),
        custom={
            "start": start_datetime.isoformat(),
            "end": end_datetime.isoformat(),
            "location": location,
            "is_online_meeting": is_online_meeting,
            "organizer": organizer_name,
            "recurrence": recurrence_pattern,
        }
    )
)
```

- Sync window: configurable (default: past 30 days + next 30 days)
- Recurring events: ingest each occurrence separately
- Link to Teams meeting if `isOnlineMeeting` is true (cross-reference with Teams connector)

### FR-4: Incremental Sync

**Email:**
- Use Microsoft Graph delta queries (`/me/messages/delta`)
- Store delta token after each sync
- Delta returns only new/modified/deleted messages since last token
- Handle deleted messages: remove from knowledge base

**Calendar:**
- Use `calendarView` with a sliding window
- Track event IDs and last-modified timestamps
- Re-process modified events

### FR-5: Rate Limiting

- Microsoft Graph limits: 10,000 requests per 10 minutes per app per tenant
- Implement token bucket rate limiter shared across all MS Graph connectors
- Batch requests where possible (max 20 per batch via `$batch` endpoint)

## Non-Functional Requirements

- Delta sync should complete in < 60 seconds for typical daily email volume
- Must not mark emails as read or modify any data (read-only)
- Must handle large mailboxes (10K+ emails) for initial sync (paginated, throttled)
- Calendar sync window is configurable

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/connectors/outlook/status` | Sync status (email + calendar) |
| POST | `/api/connectors/outlook/sync` | Trigger manual sync |
| PUT | `/api/connectors/outlook/config` | Update filter settings |

## Testing Strategy

### Unit Tests
- Test email thread grouping by conversationId
- Test email body extraction (plain text, HTML fallback)
- Test calendar event processing
- Test delta token management
- Test filter application (folder, sender domain, date range)
- Test rate limiter logic

### Integration Tests
- Test full email sync flow with mocked Graph API responses
- Test delta query sync (initial + incremental)
- Test calendar view sync with mock events
- Test thread update when new email arrives in existing conversation

### Test Fixtures
- Mocked Graph API email responses (threads, attachments, various formats)
- Mocked calendar event responses (single, recurring, online meetings)
- Delta query responses (new messages, deletions)

## Dependencies

- F-002 (Knowledge Engine Core) — for document ingestion pipeline
- F-003 (Teams Connector) — shared Microsoft Graph auth module

## Acceptance Criteria

- [ ] Emails are ingested with correct thread grouping
- [ ] Calendar events are ingested with attendee and location metadata
- [ ] Delta queries enable efficient incremental email sync
- [ ] Configurable folder and sender domain filters work correctly
- [ ] Rate limiting prevents 429 errors from Microsoft Graph
- [ ] Deleted emails/events are removed from the knowledge base
- [ ] Online meeting events cross-reference Teams transcript data
- [ ] Connector does not modify any emails or calendar events
