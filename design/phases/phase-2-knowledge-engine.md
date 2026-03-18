# Phase 2 — Knowledge Engine

**Jira Epic:** NXP-3
**Dependencies:** NXP-2 (Phase 1)

Hybrid vector + graph knowledge store with LlamaIndex orchestration, ingestion pipeline, and retrieval.

---

## Stories

| Jira Key | Title | Subtasks | Spec |
|----------|-------|----------|------|
| NXP-36 | Set Up LanceDB Vector Store | NXP-40 | F-002 FR-3 |
| NXP-37 | Set Up Kuzu Graph Database | NXP-41 | F-002 FR-4 |
| NXP-38 | Integrate LlamaIndex PropertyGraphIndex | NXP-42, NXP-43, NXP-44 | F-002 FR-2, FR-5 |
| NXP-39 | Implement Engine API Endpoints | NXP-45 | F-002 API |

## Subtasks

| Jira Key | Title | Parent |
|----------|-------|--------|
| NXP-40 | Initialize LanceDB and Implement Vector Operations | NXP-36 |
| NXP-41 | Initialize Kuzu and Create Schema | NXP-37 |
| NXP-42 | Configure PropertyGraphIndex with Dual Backends | NXP-38 |
| NXP-43 | Implement Document Ingestion Pipeline | NXP-38 |
| NXP-44 | Implement Hybrid Retrieval | NXP-38 |
| NXP-45 | Create Engine REST Endpoints | NXP-39 |

## Key Outputs

- `backend/src/nexuspkm/engine/vector_store.py` — LanceDB store/search/delete
- `backend/src/nexuspkm/engine/graph_store.py` — Kuzu schema + CRUD
- `backend/src/nexuspkm/engine/index.py` — PropertyGraphIndex wiring
- `backend/src/nexuspkm/engine/ingestion.py` — chunk → embed → store → extract pipeline
- `backend/src/nexuspkm/engine/retrieval.py` — hybrid vector + graph retrieval
- `POST /api/engine/ingest`, `GET /api/engine/stats`, `GET /api/engine/status`

## Parallelization

NXP-36 and NXP-37 can run in parallel. NXP-38 depends on both. NXP-39 depends on NXP-38.
