# F-009: Apple Notes Connector

**Spec Version:** 1.0
**Date:** 2026-03-16
**ADR Reference:** ADR-004
**Priority:** V2

## Overview

A macOS-specific connector that ingests notes from Apple Notes. Since Apple Notes has no official API, this connector uses the macOS AppleScript bridge (`osascript`) as the primary method, with the SQLite database as a fallback option.

## User Stories

- As a user, I want my Apple Notes automatically ingested into my knowledge base
- As a user, I want the note folder structure preserved as metadata
- As a user, I want only new or modified notes synced on subsequent runs

## Functional Requirements

### FR-1: Extraction Method — AppleScript (Primary)

```python
import subprocess
import json

APPLESCRIPT = '''
tell application "Notes"
    set noteList to {}
    repeat with eachNote in notes
        set noteData to {id: (id of eachNote) as text, ¬
            name: (name of eachNote) as text, ¬
            body: (body of eachNote) as text, ¬
            folder: (name of container of eachNote) as text, ¬
            created: (creation date of eachNote) as text, ¬
            modified: (modification date of eachNote) as text}
        set end of noteList to noteData
    end repeat
    return noteList
end tell
'''

async def fetch_notes() -> list[dict]:
    result = subprocess.run(
        ["osascript", "-e", APPLESCRIPT],
        capture_output=True, text=True, timeout=120
    )
    return parse_applescript_output(result.stdout)
```

- AppleScript returns HTML body content
- Convert HTML → plain text for embedding, preserve HTML for display
- Handle permission prompt (macOS will ask user to grant Notes access on first run)
- Timeout: 120 seconds for large note collections

### FR-2: Extraction Method — SQLite (Fallback)

Database location: `~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite`

```sql
SELECT
    n.ZNOTE as note_id,
    n.ZTITLE as title,
    nb.ZDATA as body_data,  -- Compressed/encoded
    f.ZTITLE as folder_name,
    n.ZCREATIONDATE as created,
    n.ZMODIFICATIONDATE as modified
FROM ZICCLOUDSYNCINGOBJECT n
JOIN ZNOTEBODY nb ON n.ZBODY = nb.Z_PK
LEFT JOIN ZICCLOUDSYNCINGOBJECT f ON n.ZFOLDER = f.Z_PK
WHERE n.ZMARKEDFORDELETION != 1
```

- SQLite approach is faster but more fragile (Apple may change the schema between macOS versions)
- Body data may be compressed (gzip) and encoded — requires decompression
- Configuration flag to choose method: `extraction_method: applescript | sqlite`

### FR-3: Content Processing

- HTML body → convert to markdown using `markdownify` or `html2text`
- Extract embedded images: skip or extract alt text
- Extract checklists: preserve as markdown task lists
- Extract tables: convert to markdown tables
- Strip Apple Notes-specific HTML attributes

### FR-4: Document Transformation

```python
Document(
    id=generate_uuid(),
    content=markdown_content,
    metadata=DocumentMetadata(
        source_type=SourceType.APPLE_NOTE,
        source_id=note_id,
        title=note_title,
        tags=[],  # Apple Notes doesn't have native tags
        created_at=created_date,
        updated_at=modified_date,
        synced_at=datetime.utcnow(),
        custom={
            "folder": folder_name,
            "extraction_method": "applescript",
            "has_images": bool,
            "has_checklists": bool,
        }
    )
)
```

### FR-5: Incremental Sync

- Track note_id → modification_date mapping
- On sync: fetch all notes, compare modification dates, only process changed notes
- Detect deletions: notes in sync state but not in current fetch → remove from knowledge base
- Note: AppleScript method fetches all notes each time (no delta query) — compare locally

## Non-Functional Requirements

- macOS only — connector must gracefully disable on other platforms
- Must handle Apple Notes permission dialog on first run
- Must not modify any notes (read-only)
- Large collections (1000+ notes) should complete initial sync in < 5 minutes

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/connectors/apple-notes/status` | Sync status |
| POST | `/api/connectors/apple-notes/sync` | Trigger manual sync |
| PUT | `/api/connectors/apple-notes/config` | Update settings |

## Testing Strategy

### Unit Tests
- Test HTML → markdown conversion with sample Apple Notes HTML
- Test checklist and table extraction
- Test incremental sync logic (new/modified/deleted detection)
- Test AppleScript output parsing
- Test platform detection (disable on non-macOS)

### Integration Tests
- Test full sync flow with mocked AppleScript output
- Test SQLite extraction with a copy of a NoteStore.sqlite

### Test Fixtures
- Sample Apple Notes HTML content (various formatting)
- Sample AppleScript output (list of notes)
- Copy of a NoteStore.sqlite schema for SQLite tests

## Dependencies

- F-002 (Knowledge Engine Core) — for document ingestion pipeline

## Acceptance Criteria

- [ ] AppleScript extraction retrieves all notes with metadata
- [ ] HTML content is correctly converted to markdown
- [ ] Checklists and tables are preserved in conversion
- [ ] Incremental sync only processes new/modified notes
- [ ] Deleted notes are removed from the knowledge base
- [ ] Connector gracefully disables on non-macOS platforms
- [ ] 1000+ note collection syncs in < 5 minutes
