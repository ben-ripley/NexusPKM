# F-004: Obsidian Notes Connector

**Spec Version:** 1.0
**Date:** 2026-03-16
**ADR Reference:** ADR-004

## Overview

Ingests markdown notes from an Obsidian vault by watching the filesystem for changes. Handles Obsidian-specific syntax (wikilinks, tags, callouts, embeds) and YAML frontmatter. Supports initial full scan and incremental change detection.

## User Stories

- As a user, I want my Obsidian notes automatically ingested when I create or edit them
- As a user, I want Obsidian-specific syntax (wikilinks, tags) preserved and extracted as metadata
- As a user, I want to exclude certain folders (e.g., .obsidian, .trash) from ingestion
- As a user, I want deleted notes removed from the knowledge base

## Functional Requirements

### FR-1: Vault Discovery and Configuration

```yaml
connectors:
  obsidian:
    enabled: true
    type: obsidian
    sync_interval: 300
    settings:
      vault_path: /Users/bripley/ObsidianVault
      exclude_patterns:
        - ".obsidian/**"
        - ".trash/**"
        - "templates/**"
        - "*.excalidraw.md"
      include_extensions:
        - ".md"
```

- Validate vault path exists and is readable
- Resolve relative paths from config root

### FR-2: Filesystem Watching

- Use `watchfiles` (Rust-based, cross-platform) for filesystem change detection
- Event types: created, modified, deleted
- Debounce rapid changes (e.g., autosave) — 2-second debounce window
- On startup: perform full scan to detect changes since last sync
- During runtime: watch for real-time changes

### FR-3: Markdown Parsing

Parse each `.md` file to extract:

1. **YAML Frontmatter**: parse between `---` delimiters
   ```yaml
   ---
   title: Meeting Notes 2026-03-16
   tags: [meeting, project-x]
   date: 2026-03-16
   ---
   ```

2. **Wikilinks**: extract `[[link-target]]` and `[[link-target|display text]]`
   - Store as metadata for relationship mapping
   - Resolve to other documents in the vault when possible

3. **Tags**: extract `#tag` and nested `#parent/child` tags
   - Store as document tags in metadata

4. **Content**: full markdown text (with Obsidian syntax intact for display, plain text version for embedding)

5. **Callouts**: extract `> [!type] Title` blocks and their content

6. **Embeds**: note `![[embedded-note]]` references for relationship tracking

### FR-4: Document Transformation

```python
Document(
    id=generate_uuid(),
    content=plain_text_content,  # Stripped of Obsidian syntax for embedding
    metadata=DocumentMetadata(
        source_type=SourceType.OBSIDIAN_NOTE,
        source_id=relative_file_path,  # Relative to vault root
        title=frontmatter.get("title", filename_without_extension),
        tags=extracted_tags,
        created_at=file_creation_time,
        updated_at=file_modification_time,
        synced_at=datetime.utcnow(),
        custom={
            "frontmatter": frontmatter_dict,
            "wikilinks": extracted_wikilinks,
            "embeds": extracted_embeds,
            "vault_path": relative_file_path,
            "raw_markdown": original_markdown,
        }
    )
)
```

### FR-5: Incremental Sync

- Track file state: path → (modification_time, content_hash)
- On change detection:
  - **Created**: ingest new document
  - **Modified**: update existing document (re-embed, re-extract entities)
  - **Deleted**: remove document from vector store and graph
- Persist sync state to `data/.sync/obsidian_state.json`

### FR-6: Deletion Handling

- When a file is deleted: remove from LanceDB (by source_id), remove Document node from Kuzu, clean up orphaned relationships
- When a file is renamed: treat as delete + create (filesystem watchers see this as two events)

## Non-Functional Requirements

- File watcher must not consume excessive CPU (use efficient OS-level notifications)
- Initial vault scan of 1000+ notes should complete in < 30 seconds (excluding embedding)
- Debounce prevents redundant processing during rapid edits
- Connector must not modify any files in the vault (read-only)

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/connectors/obsidian/status` | Sync status, file count, last scan time |
| POST | `/api/connectors/obsidian/sync` | Trigger manual full scan |
| PUT | `/api/connectors/obsidian/config` | Update vault path and settings |

## Testing Strategy

### Unit Tests
- Test markdown parsing: frontmatter extraction, wikilink extraction, tag extraction
- Test Obsidian-specific syntax handling (callouts, embeds, nested tags)
- Test Document transformation from parsed markdown
- Test exclude pattern matching
- Test sync state tracking (create/modify/delete detection)
- Test debounce logic

### Integration Tests
- Test full scan of a sample vault directory
- Test filesystem watcher detects create/modify/delete events
- Test deletion cascades to vector store and graph

### Test Fixtures
- Sample Obsidian vault directory with 10-20 markdown files
- Files with various frontmatter schemas
- Files with wikilinks, tags, callouts, embeds
- Edge cases: empty files, files without frontmatter, binary files mixed in

## Dependencies

- F-002 (Knowledge Engine Core) — for document ingestion pipeline

## Acceptance Criteria

- [ ] Full vault scan ingests all .md files respecting exclude patterns
- [ ] YAML frontmatter is correctly parsed and stored as metadata
- [ ] Wikilinks, tags, and embeds are extracted and stored
- [ ] Filesystem watcher detects new, modified, and deleted files
- [ ] Deleted files are removed from both vector store and graph
- [ ] Debounce prevents redundant processing of rapid changes
- [ ] Connector does not modify any files in the vault
- [ ] 1000-file vault initial scan completes in < 30 seconds
