# Phase 3 — Connector Framework & V1 Connectors

**Jira Epic:** NXP-4
**Dependencies:** NXP-3 (Phase 2)

Pluggable connector framework with sync scheduler, Microsoft Graph auth, and Teams + Obsidian connectors.

---

## Stories

| Jira Key | Title | Subtasks | Spec |
|----------|-------|----------|------|
| NXP-46 | Implement Connector Framework | NXP-51, NXP-52 | ADR-004 |
| NXP-47 | Implement Microsoft Graph Authentication | NXP-53 | F-003 FR-1 |
| NXP-48 | Implement Teams Transcript Connector | NXP-54, NXP-55, NXP-56 | F-003 |
| NXP-49 | Implement Obsidian Notes Connector | NXP-57, NXP-58 | F-004 |
| NXP-50 | Implement Connector API Endpoints | NXP-59 | — |

## Subtasks

| Jira Key | Title | Parent |
|----------|-------|--------|
| NXP-51 | Create BaseConnector and Registry | NXP-46 |
| NXP-52 | Implement Sync Scheduler | NXP-46 |
| NXP-53 | Implement Device Code OAuth2 Flow | NXP-47 |
| NXP-54 | Implement Meeting Discovery | NXP-48 |
| NXP-55 | Implement VTT Transcript Parsing | NXP-48 |
| NXP-56 | Implement Document Transformation and Sync | NXP-48 |
| NXP-57 | Implement Markdown Parser | NXP-49 |
| NXP-58 | Implement Filesystem Watcher | NXP-49 |
| NXP-59 | Create Connector REST Endpoints | NXP-50 |

## Key Outputs

- `backend/src/nexuspkm/connectors/base.py` — BaseConnector, ConnectorRegistry
- `backend/src/nexuspkm/connectors/scheduler.py` — APScheduler-based sync
- `backend/src/nexuspkm/connectors/microsoft/auth.py` — device code OAuth2, token storage
- `backend/src/nexuspkm/connectors/microsoft/vtt_parser.py` — VTT → TranscriptSegments (standalone parser)
- `backend/src/nexuspkm/connectors/microsoft/teams.py` — meeting discovery + calls vtt_parser + Document transformation
- `backend/src/nexuspkm/connectors/obsidian/` — markdown parser + filesystem watcher
- `GET /api/connectors/status`, `POST /api/connectors/{name}/sync`

## Parallelization

NXP-46 first. NXP-47 depends on NXP-46. NXP-48 depends on NXP-47. NXP-49 depends only on NXP-46 (can run in parallel with NXP-47/48).
