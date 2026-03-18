# Phase 4 — Entity & Relationship Intelligence

**Jira Epic:** NXP-5
**Dependencies:** NXP-3 (Phase 2), NXP-4 (Phase 3, for source documents)

LLM-powered entity extraction, deduplication, contradiction detection, and async processing queue.

---

## Stories

| Jira Key | Title | Subtasks | Spec |
|----------|-------|----------|------|
| NXP-60 | Implement Entity Extraction Pipeline | NXP-70–73 | F-006 |
| NXP-61 | Implement Entity API Endpoints | NXP-74 | F-006 API |

## Subtasks

| Jira Key | Title | Parent |
|----------|-------|--------|
| NXP-70 | Create Extraction Prompts and Parser | NXP-60 |
| NXP-71 | Implement Entity Deduplication | NXP-60 |
| NXP-72 | Implement Contradiction Detection | NXP-60 |
| NXP-73 | Implement Background Extraction Queue | NXP-60 |
| NXP-74 | Create Entity and Relationship Endpoints | NXP-61 |

## Key Outputs

- `backend/src/nexuspkm/intelligence/extraction.py` — LLM extraction + JSON parser
- `backend/src/nexuspkm/intelligence/deduplication.py` — name/email/fuzzy matching
- `backend/src/nexuspkm/intelligence/contradictions.py` — conflict detection + resolution
- `backend/src/nexuspkm/intelligence/queue.py` — persistent async extraction queue
- `GET /api/entities`, `GET /api/entities/{id}`, `POST /api/entities/merge`
- `GET /api/contradictions`, `POST /api/contradictions/{id}/resolve`
