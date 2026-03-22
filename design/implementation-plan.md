# NexusPKM Implementation Plan

**Version:** 2.0
**Date:** 2026-03-18

Jira (project **NXP**) is the source of truth for all issue details, acceptance criteria, and status.
This file provides the dependency overview and links to per-phase breakdowns.

---

## Epic Dependency Graph

```
Epic 1: Infrastructure ──► Epic 2: Core Backend ──► Epic 3: Knowledge Engine
                                                          │
                                                          ▼
                                              Epic 4: V1 Connectors
                                                          │
                                              Epic 5: Entity Intelligence
                                                          │
                                                          ▼
                                              Epic 6: Frontend Core
                                                          │
                                              ┌───────────┼───────────┐
                                              ▼           ▼           ▼
                                      Epic 7: V2    Epic 8: V3   (parallel)
                                      Connectors    + Advanced
                                                          │
                                                          ▼
                                              Epic 9: Automation
```

---

## Phase Overview

| Phase | Epic | Jira Key | Description | Depends On |
|-------|------|----------|-------------|------------|
| 0 | Epic 1 | NXP-1 | Project Infrastructure & DevOps Setup | — |
| 1 | Epic 2 | NXP-2 | Core Backend Architecture | NXP-1 |
| 2 | Epic 3 | NXP-3 | Knowledge Engine | NXP-2 |
| 3 | Epic 4 | NXP-4 | Connector Framework & V1 Connectors | NXP-3 |
| 4 | Epic 5 | NXP-5 | Entity & Relationship Intelligence | NXP-3, NXP-4 |
| 5 | Epic 6 | NXP-6 | Frontend Core (F-008, F-014) — incl. Electron packaging (NXP-97, 98, 99) | NXP-3, NXP-5 |
| 6 | Epic 7 | NXP-7 | V2 Connectors (Apple Notes, Outlook) | NXP-4 |
| 7 | Epic 8 | NXP-8 | V3 Connector & Advanced Features | NXP-4, NXP-5, NXP-6 |
| 8 | Epic 9 | NXP-9 | Automation & Extensibility | NXP-8 |

---

## Per-Phase Details

- [Phase 0 — Infrastructure](phases/phase-0-infrastructure.md)
- [Phase 1 — Core Backend](phases/phase-1-core-backend.md)
- [Phase 2 — Knowledge Engine](phases/phase-2-knowledge-engine.md)
- [Phase 3 — Connectors V1](phases/phase-3-connectors-v1.md)
- [Phase 4 — Entity Intelligence](phases/phase-4-entity-intelligence.md)
- [Phase 5 — Frontend Core](phases/phase-5-frontend-core.md)
- [Phase 6 — Connectors V2](phases/phase-6-connectors-v2.md)
- [Phase 7 — V3 + Advanced](phases/phase-7-v3-advanced.md)
- [Phase 8 — Automation](phases/phase-8-automation.md)
