# Phase 7 — V3 Connector & Advanced Features

**Jira Epic:** NXP-8
**Dependencies:** NXP-4 (Phase 3), NXP-5 (Phase 4), NXP-6 (Phase 5)

JIRA connector, schedule and task management, and proactive context surfacing.

---

## Stories

| Jira Key | Title | Subtasks | Spec |
|----------|-------|----------|------|
| NXP-85 | Implement JIRA Connector | NXP-90 | F-011 |
| NXP-86 | Implement Schedule & Task Management | NXP-91, NXP-92 | F-012 |
| NXP-87 | Implement Proactive Context Surfacing | NXP-93, NXP-94 | F-013 |

## Subtasks

| Jira Key | Title | Parent |
|----------|-------|--------|
| NXP-90 | Implement JIRA Issue Sync | NXP-85 |
| NXP-91 | Implement Priority Scoring and Digest | NXP-86 |
| NXP-92 | Implement Schedule and Workload UI | NXP-86 |
| NXP-93 | Implement Background Scanners and Notifications | NXP-87 |
| NXP-94 | Implement Notification UI | NXP-87 |

## Key Outputs

- `backend/src/nexuspkm/connectors/jira/` — JQL-based issue + comment sync
- `backend/src/nexuspkm/services/schedule.py` — priority scoring, daily digest
- `frontend/src/pages/Schedule.tsx` + workload + action item components
- `backend/src/nexuspkm/services/context_surfacing.py` — meeting prep, related content
- `backend/src/nexuspkm/services/notifications.py` — SQLite-backed notification store
- `frontend/src/components/notifications/` — bell, panel, meeting prep card

## Parallelization

NXP-85 is independent of NXP-86/87. NXP-86 and NXP-87 both depend on NXP-5 (entity data) and NXP-7 (calendar via NXP-84).
