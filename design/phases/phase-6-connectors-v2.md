# Phase 6 — V2 Connectors

**Jira Epic:** NXP-7
**Dependencies:** NXP-4 (Phase 3)

Apple Notes and Outlook (email + calendar) connectors.

---

## Stories

| Jira Key | Title | Subtasks | Spec |
|----------|-------|----------|------|
| NXP-68 | Implement Apple Notes Connector | NXP-82 | F-009 |
| NXP-69 | Implement Outlook Connector | NXP-83, NXP-84 | F-010 |

## Subtasks

| Jira Key | Title | Parent |
|----------|-------|--------|
| NXP-82 | Implement AppleScript Extraction and Connector | NXP-68 |
| NXP-83 | Implement Email Ingestion | NXP-69 |
| NXP-84 | Implement Calendar Ingestion | NXP-69 |

## Key Outputs

- `backend/src/nexuspkm/connectors/apple_notes/` — osascript bridge, HTML-to-markdown
- `backend/src/nexuspkm/connectors/microsoft/outlook_email.py` — delta query email sync
- `backend/src/nexuspkm/connectors/microsoft/outlook_calendar.py` — sliding window calendar sync

## Parallelization

NXP-68 and NXP-69 are independent and can run in parallel. NXP-69 reuses MS Graph auth from NXP-47.
