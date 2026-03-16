# F-003: Teams Transcript Connector

**Spec Version:** 1.0
**Date:** 2026-03-16
**ADR Reference:** ADR-004

## Overview

Ingests meeting transcripts from Microsoft Teams via the Microsoft Graph API. Transcripts include speaker-attributed text, meeting metadata (participants, time, duration), and are transformed into the common Document schema for processing by the knowledge engine.

## User Stories

- As a user, I want my Teams meeting transcripts automatically ingested so I can search and query them
- As a user, I want to see who said what in a meeting transcript
- As a user, I want only new transcripts synced, not re-fetching everything each time
- As a user, I want to see the sync status of my Teams connector

## Functional Requirements

### FR-1: Microsoft Graph OAuth2 Authentication

- Register an Azure AD application with the following permissions:
  - `OnlineMeetingTranscript.Read` (delegated)
  - `OnlineMeeting.Read` (delegated)
  - `User.Read` (delegated)
- Authentication flow: **Device Code Flow** (user-friendly for local CLI/app, no redirect URI needed)
- Token storage: encrypted on disk at `data/.tokens/ms_graph.json` (gitignored)
- Automatic token refresh before expiry
- Re-authentication prompt when refresh token expires

### FR-2: Meeting Discovery

```
GET /me/onlineMeetings
  ?$filter=startDateTime ge {since_timestamp}
  &$orderby=startDateTime desc
  &$top=50
```

- Paginate through all meetings since last sync
- Filter for meetings that have transcripts available
- Store meeting metadata: title, start time, end time, organizer, participants

### FR-3: Transcript Retrieval

```
GET /me/onlineMeetings/{meeting-id}/transcripts
GET /me/onlineMeetings/{meeting-id}/transcripts/{transcript-id}/content
  ?$format=text/vtt
```

- Retrieve transcript content in VTT format (includes timestamps and speaker labels)
- Parse VTT format to extract:
  - Speaker name and timestamp for each utterance
  - Full text content (concatenated utterances)
  - Speaker-to-text mapping for attribution

### FR-4: Transcript Parsing

```python
class TranscriptSegment(BaseModel):
    speaker: str
    start_time: str          # HH:MM:SS.mmm
    end_time: str
    text: str

class ParsedTranscript(BaseModel):
    meeting_id: str
    title: str
    date: datetime
    duration_minutes: int
    participants: list[str]
    segments: list[TranscriptSegment]
    full_text: str           # Concatenated for embedding
```

- Parse VTT cues into `TranscriptSegment` objects
- Extract unique speakers list
- Generate full text with speaker labels (e.g., "John Smith: We should prioritize the API work...")
- Handle edge cases: empty transcripts, missing speaker labels, overlapping timestamps

### FR-5: Document Transformation

Transform `ParsedTranscript` into common `Document` schema:

```python
Document(
    id=generate_uuid(),
    content=parsed.full_text,
    metadata=DocumentMetadata(
        source_type=SourceType.TEAMS_TRANSCRIPT,
        source_id=meeting_id,
        title=f"Meeting: {parsed.title}",
        participants=parsed.participants,
        created_at=parsed.date,
        updated_at=parsed.date,
        synced_at=datetime.utcnow(),
        custom={
            "duration_minutes": parsed.duration_minutes,
            "segments": [s.model_dump() for s in parsed.segments],
        }
    )
)
```

### FR-6: Incremental Sync

- Store last successful sync timestamp in sync state
- On subsequent syncs, only fetch meetings with `startDateTime` after the last sync
- Handle meeting updates: if a transcript is updated after initial sync, re-process it
- Configurable sync interval (default: 1 hour)

### FR-7: Rate Limiting

- Respect Microsoft Graph rate limits (throttling returns 429)
- Implement exponential backoff with jitter on 429 responses
- Maximum 3 retries per request
- Log rate limit events

## Non-Functional Requirements

- Sync must run in the background without blocking the UI
- Token refresh must be transparent to the user
- Connector must gracefully handle meetings without transcription enabled
- VTT parsing must handle malformed VTT content without crashing

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/connectors/teams/authenticate` | Initiate device code auth flow |
| GET | `/api/connectors/teams/status` | Sync status, last sync time, document count |
| POST | `/api/connectors/teams/sync` | Trigger manual sync |
| PUT | `/api/connectors/teams/config` | Update connector settings |

## Testing Strategy

### Unit Tests
- Test VTT parsing with sample transcript files (valid, malformed, empty)
- Test Document transformation from ParsedTranscript
- Test incremental sync logic (timestamp filtering)
- Test rate limit backoff calculation
- Test token refresh logic

### Integration Tests
- Test full sync flow with mocked Microsoft Graph API responses
- Test OAuth2 device code flow with mocked auth endpoints
- Test pagination handling with multi-page meeting lists

### Test Fixtures
- Sample VTT transcript files (2-3 speakers, various lengths)
- Mocked Graph API responses for meeting lists and transcript content
- Mocked OAuth2 token responses

## Dependencies

- F-002 (Knowledge Engine Core) — for document ingestion pipeline
- Microsoft Graph API Azure AD app registration (infrastructure setup)

## Acceptance Criteria

- [ ] Device code OAuth2 flow authenticates successfully
- [ ] Meetings with transcripts are discovered via Graph API
- [ ] VTT transcripts are parsed with correct speaker attribution
- [ ] Parsed transcripts are transformed to common Document schema
- [ ] Incremental sync only fetches new transcripts since last sync
- [ ] Rate limiting handles 429 responses with backoff
- [ ] Connector status endpoint reports accurate sync state
- [ ] Malformed/empty transcripts are handled gracefully without pipeline failure
