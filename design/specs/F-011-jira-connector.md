# F-011: JIRA Connector

**Spec Version:** 1.0
**Date:** 2026-03-16
**ADR Reference:** ADR-004
**Priority:** V3

## Overview

Ingests issues, comments, and project metadata from Atlassian JIRA via the REST API v3. Maps JIRA entities to the NexusPKM knowledge graph (issues → ActionItems, assignees → Persons, projects → Projects). Supports JQL-based filtering and incremental sync.

## User Stories

- As a user, I want my JIRA tickets searchable alongside meeting notes and emails
- As a user, I want to see which JIRA tickets relate to topics discussed in meetings
- As a user, I want to track my team's workload based on JIRA assignments
- As a user, I want to filter which JIRA projects are synced

## Functional Requirements

### FR-1: Authentication

- **API Token**: JIRA Cloud uses email + API token
- **OAuth 2.0 (3LO)**: alternative for JIRA Cloud with more granular scopes
- Configuration:
  ```yaml
  connectors:
    jira:
      enabled: true
      settings:
        base_url: https://company.atlassian.net
        auth_method: api_token  # or oauth2
        email: ${JIRA_EMAIL}
        api_token: ${JIRA_API_TOKEN}
        projects:
          - PROJ
          - TEAM
        issue_types:
          - Story
          - Bug
          - Task
          - Epic
        sync_window_days: 90
  ```

### FR-2: Issue Ingestion

```
GET /rest/api/3/search
  ?jql=project in (PROJ, TEAM) AND updated >= "-{sync_window_days}d"
  &fields=summary,description,status,assignee,reporter,priority,
          created,updated,labels,components,sprint,issuetype,
          comment,parent
  &maxResults=100
  &startAt={offset}
```

Process each issue:
```python
Document(
    id=generate_uuid(),
    content=f"{issue_key}: {summary}\n\n{description}\n\n{comments_text}",
    metadata=DocumentMetadata(
        source_type=SourceType.JIRA_ISSUE,
        source_id=issue_key,  # e.g., "PROJ-123"
        title=f"{issue_key}: {summary}",
        author=reporter_name,
        tags=labels + [f"component:{c}" for c in components],
        url=f"{base_url}/browse/{issue_key}",
        created_at=created_datetime,
        updated_at=updated_datetime,
        synced_at=datetime.utcnow(),
        custom={
            "issue_type": issue_type,
            "status": status_name,
            "priority": priority_name,
            "assignee": assignee_name,
            "reporter": reporter_name,
            "sprint": sprint_name,
            "parent_key": parent_key,
            "components": components,
            "story_points": story_points,
        }
    )
)
```

### FR-3: Entity Mapping

| JIRA Entity | NexusPKM Entity | Relationship |
|---|---|---|
| Issue | ActionItem | — |
| Assignee | Person | ASSIGNED_TO |
| Reporter | Person | MENTIONED_IN |
| Project | Project | TAGGED_WITH |
| Sprint | Topic | TAGGED_WITH |
| Parent Issue | ActionItem | BLOCKS / FOLLOWED_UP_BY |
| Components | Topic | TAGGED_WITH |

### FR-4: Comment Ingestion

- Fetch all comments per issue
- Append chronologically to the issue document content
- Extract comment authors as Person entities
- Format: `[Author Name - Date]: Comment text`

### FR-5: Incremental Sync

- Use JQL `updated >= "-{hours}h"` to find recently changed issues
- Track per-issue `updated` timestamp
- Re-process issues when updated (re-ingest document, update entities)
- Detect deleted issues: issues in sync state but returning 404 → remove from knowledge base

### FR-6: Workload Data Extraction

For team workload management (F-012):
- Extract per-person: open issues count, story points, status distribution
- Extract per-sprint: completion rate, scope changes
- Expose as structured data via the entity API

## Non-Functional Requirements

- Must handle large JIRA projects (10K+ issues) for initial sync
- Paginated sync with configurable batch size
- Must not modify any JIRA data (read-only)
- JIRA API rate limits: respect `X-RateLimit-*` headers

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/connectors/jira/status` | Sync status |
| POST | `/api/connectors/jira/sync` | Trigger manual sync |
| PUT | `/api/connectors/jira/config` | Update project list and filters |

## Testing Strategy

### Unit Tests
- Test JQL construction from configuration
- Test issue-to-Document transformation
- Test entity mapping (issue → ActionItem, assignee → Person)
- Test comment concatenation and formatting
- Test incremental sync timestamp logic

### Integration Tests
- Test full sync flow with mocked JIRA API responses
- Test pagination handling (multi-page issue lists)
- Test incremental sync (changed issues only)

### Test Fixtures
- Mocked JIRA API responses (issue search results, issue details, comments)
- Various issue types and field combinations

## Dependencies

- F-002 (Knowledge Engine Core) — for document ingestion pipeline
- F-006 (Entity Extraction) — for entity mapping to graph

## Acceptance Criteria

- [ ] Issues are ingested with all relevant metadata
- [ ] Comments are included in issue documents
- [ ] JIRA entities map correctly to knowledge graph (Person, Project, ActionItem)
- [ ] JQL filters restrict sync to configured projects and issue types
- [ ] Incremental sync only processes recently updated issues
- [ ] Workload data (open issues per person, story points) is extractable
- [ ] Connector handles 10K+ issue projects via pagination
- [ ] No JIRA data is modified
