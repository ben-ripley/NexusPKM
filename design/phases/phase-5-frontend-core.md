# Phase 5 — Frontend Core

**Jira Epic:** NXP-6
**Dependencies:** NXP-3 (Phase 2), NXP-5 (Phase 4)

Application shell, chat interface, search, dashboard, graph explorer, and settings page.

---

## Stories

| Jira Key | Title | Subtasks | Spec |
|----------|-------|----------|------|
| NXP-62 | Implement Application Shell | NXP-75 | F-008 FR-1, FR-3 |
| NXP-63 | Implement Chat Interface | NXP-76, NXP-77 | F-005 |
| NXP-64 | Implement Search Interface | NXP-78 | F-007 |
| NXP-65 | Implement Dashboard | NXP-79 | F-008 |
| NXP-66 | Implement Graph Explorer | NXP-80 | F-008 graph |
| NXP-67 | Implement Settings Page | NXP-81 | — |

## Subtasks

| Jira Key | Title | Parent |
|----------|-------|--------|
| NXP-75 | Create Layout, Routing, and Theme | NXP-62 |
| NXP-76 | Create Chat WebSocket Backend | NXP-63 |
| NXP-77 | Create Chat UI Components | NXP-63 |
| NXP-78 | Create Search UI Components | NXP-64 |
| NXP-79 | Create Dashboard Components | NXP-65 |
| NXP-80 | Create Graph Visualization | NXP-66 |
| NXP-81 | Create Settings UI | NXP-67 |

## Key Outputs

- `frontend/src/components/layout/` — AppShell, Sidebar, TopBar
- `frontend/src/pages/` — Chat, Search, Dashboard, GraphExplorer, Settings
- `frontend/src/components/chat/` — streaming messages, source cards, session list
- `frontend/src/components/search/` — search bar, results, filters
- `frontend/src/components/dashboard/` — activity feed, connector status, stats
- `frontend/src/components/graph/` — force-directed graph canvas + controls
- `backend/src/nexuspkm/api/chat.py` — WebSocket streaming endpoint (cross-phase: backend work within NXP-76)
- `frontend/src/hooks/` — useChat, useSearch, useDashboard, useGraphData
- `frontend/src/services/` — websocket.ts, api.ts

## Parallelization

NXP-62 first (shell + routing required by all pages). NXP-63 also needs backend (NXP-76) which can start in parallel. NXP-64, NXP-65, NXP-66, NXP-67 can all proceed in parallel after NXP-62.
