---
title: Connectors
nav_order: 3
---

# Connectors

Connectors are the data sources Nexus PKM pulls content from. Each connector runs on a schedule in the background, fetching new and changed content since
the last sync. All connectors are read-only — they never write back to the source system.

---

## Enabling a connector

All connector settings live in `config/connectors.yaml`. Set `enabled: true` for each connector you want to use. API credentials must be provided as environment variables (not in the config file).

After enabling a connector, trigger an initial sync from the Settings page or via the API:

```bash
curl -X POST http://127.0.0.1:8000/api/connectors/{name}/sync
```

---

## Microsoft Teams

**What it ingests:** Meeting transcripts — the spoken content of your recorded Teams meetings, with speaker attribution and timestamps.

**How it works:** Uses the Microsoft Graph API to fetch meeting transcripts in VTT format (the same format used for video subtitles). Each transcript becomes a document with the full conversation text and speaker labels preserved ("Jane Smith: We should ship this by Friday…").

**Prerequisites:** Requires an Azure AD app registration with the following delegated permissions:
- `OnlineMeetingTranscript.Read`
- `OnlineMeeting.Read`
- `User.Read`

**Authentication:** Device Code Flow — on first use, the application displays a short code you enter at microsoft.com/devicelogin to authorize access. Tokens are stored encrypted at `data/.tokens/ms_graph.json` and refreshed automatically.

**Config:**
```yaml
# config/connectors.yaml
teams:
  enabled: true
  sync_interval_minutes: 30
  # Only fetch transcripts from meetings on or after this date on the initial sync.
  # Has no effect on subsequent incremental syncs.
  # transcript_lookback_date: "2024-01-01"
```

**Environment variables:**
```bash
MS_TENANT_ID=your-tenant-id
MS_CLIENT_ID=your-app-client-id
MS_CLIENT_SECRET=your-app-client-secret
```

**Sync behavior:** Incremental — only meetings that started after the last successful sync are fetched. If Teams transcription wasn't enabled for a meeting, it's skipped gracefully. On the initial sync, `lookback_date` limits how far back the import reaches; without it, all available transcripts are fetched (subject to your Teams tenant's retention policy).

**Trigger authentication:**
```bash
curl -X POST http://127.0.0.1:8000/api/connectors/teams/authenticate
```

---

## Microsoft Outlook (Email & Calendar)

**What it ingests:** Email threads from your configured folders, and calendar events including attendees, location, and meeting body.

**How it works:** Uses the Microsoft Graph API, sharing the same OAuth2 authentication as the Teams connector. Emails are grouped by conversation thread so related messages appear as a single document. Calendar events are ingested as documents with attendee lists and descriptions.

**Prerequisites:** Same Azure AD app registration as Teams, with additional delegated permissions:
- `Mail.Read`
- `Calendars.Read`

**Config:**
```yaml
# config/connectors.yaml
outlook:
  enabled: true
  sync_interval_minutes: 15
  folders:
    - Inbox
    - Sent Items
  # Only fetch emails on or after this date for the initial sync.
  # Strongly recommended to prevent ingesting your entire mailbox history.
  email_lookback_date: "2024-01-01"
  # Only fetch calendar events on or after this date.
  calendar_lookback_date: "2024-01-01"
```

**Environment variables:** Shared with Teams connector (same app registration):
```bash
MS_TENANT_ID=your-tenant-id
MS_CLIENT_ID=your-app-client-id
MS_CLIENT_SECRET=your-app-client-secret
```

**Sync behavior:** Email uses Microsoft Graph **delta queries** — after the initial sync, only new and changed messages are fetched. Calendar uses a sliding window. Deleted emails and events are removed from the knowledge base.

> **Tip:** Set `email_lookback_date` before the first sync. Without it, the connector will try to import your entire mailbox history, which can take a very long time and use significant LLM tokens for entity extraction.

---

## Obsidian

**What it ingests:** Markdown notes from an Obsidian vault.

**How it works:** Watches the vault directory for file system events (created, modified, deleted) using efficient OS-level file notifications. On first run it performs a full scan; after that it responds to changes in real time with a 2-second debounce to handle autosave bursts.

Obsidian-specific syntax is handled:
- **YAML frontmatter** is parsed and stored as metadata (title, tags, dates)
- **Wikilinks** (`[[Note Title]]`) are extracted and used to map relationships between notes
- **Tags** (`#tag`, `#parent/child`) are extracted as document tags
- **Callouts** and **embeds** are parsed for relationship tracking
- The raw markdown is stored; plain text is used for embedding

**No credentials required** — access is via the local filesystem.

**Config:**
```yaml
# config/connectors.yaml
obsidian:
  enabled: true
  vault_path: ~/Documents/Obsidian   # Path to your vault
  sync_interval_minutes: 5
  exclude_patterns:
    - ".obsidian/"
    - ".trash/"
    - "templates/"
```

**Sync behavior:** Real-time file watching plus periodic full-scan verification. Deleted files are removed from both the vector store and the graph. The connector never modifies any files in your vault.

> **Screenshot placeholder:** Obsidian connector status card showing note count and last scan time

---

## JIRA

**What it ingests:** Issues (stories, bugs, tasks, epics) and their comments from configured JIRA projects.

**How it works:** Uses the JIRA REST API v3 with JQL (JIRA Query Language) to fetch issues. Each issue becomes a document containing the summary, description, and all comments concatenated chronologically. JIRA entities are mapped to the knowledge graph — assignees become Person nodes, projects become Project nodes, and issues become ActionItem nodes.

**Prerequisites:** A JIRA Cloud account with an API token. Generate one at [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens).

**Config:**
```yaml
# config/connectors.yaml
jira:
  enabled: true
  base_url: https://your-instance.atlassian.net
  sync_interval_minutes: 30
  jql_filter: "assignee = currentUser() ORDER BY updated DESC"
```

**Environment variables:**
```bash
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=your-api-token
```

**Sync behavior:** Incremental using JQL `updated >= "-Xh"` to find recently changed issues. Issues deleted in JIRA are removed from the knowledge base.

**Entity mapping:**

| JIRA | Nexus PKM graph |
|---|---|
| Issue | ActionItem |
| Assignee | Person → ASSIGNED_TO |
| Reporter | Person → MENTIONED_IN |
| Project | Project → TAGGED_WITH |
| Sprint | Topic → TAGGED_WITH |
| Parent issue | ActionItem → BLOCKS / FOLLOWED_UP_BY |

---

## Apple Notes

**What it ingests:** Notes from the Apple Notes app, including folder structure.

**How it works:** macOS-only. Uses the AppleScript bridge (`osascript`) to ask the Notes application directly for all notes. Apple Notes has no official API, so this is the supported path. The note body is HTML which is converted to markdown for embedding.

On first run, macOS will show a permission dialog asking whether to allow Nexus PKM to access Notes. You must click Allow.

**No credentials required** — access is granted by the macOS permission dialog.

**Config:**
```yaml
# config/connectors.yaml
apple_notes:
  enabled: true
  sync_interval_minutes: 15
```

**Sync behavior:** AppleScript fetches all notes; the connector compares modification dates locally to determine what's new or changed. This is less efficient than delta queries but is a limitation of AppleScript — there's no "changes since timestamp" API. For large collections (1000+ notes), the initial sync can take a few minutes.

> **Note:** This connector only works on macOS. It is automatically disabled on other platforms.

---

## Connector status

All connector statuses are visible on the Dashboard and in Settings.

```bash
# Check all connector statuses via API
curl http://127.0.0.1:8000/api/connectors/status | python3 -m json.tool
```

Each status includes:
- Current state: `active`, `syncing`, `error`, `disabled`
- Last successful sync time
- Document count ingested from this source
- Error message (if in error state)

---

## Triggering a manual sync

From the UI: click the sync button on any connector card in the Dashboard or Settings.

From the API:
```bash
curl -X POST http://127.0.0.1:8000/api/connectors/teams/sync
curl -X POST http://127.0.0.1:8000/api/connectors/outlook/sync
curl -X POST http://127.0.0.1:8000/api/connectors/obsidian/sync
curl -X POST http://127.0.0.1:8000/api/connectors/jira/sync
curl -X POST http://127.0.0.1:8000/api/connectors/apple-notes/sync
```
