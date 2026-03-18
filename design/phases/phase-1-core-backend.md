# Phase 1 — Core Backend Architecture

**Jira Epic:** NXP-2
**Dependencies:** NXP-1 (Phase 0)

Foundational backend components: configuration system, common data models, and LLM/embedding provider abstraction.

---

## Stories

| Jira Key | Title | Subtasks | Spec |
|----------|-------|----------|------|
| NXP-26 | Implement Configuration Management System | NXP-29 | Architecture §6 |
| NXP-27 | Implement Common Data Models | NXP-30 | F-002, F-005, F-006, F-007 |
| NXP-28 | Implement LLM Provider Abstraction Layer | NXP-31–35 | F-001 |

## Subtasks

| Jira Key | Title | Parent |
|----------|-------|--------|
| NXP-29 | Create Configuration Models | NXP-26 |
| NXP-30 | Create Document and Metadata Models | NXP-27 |
| NXP-31 | Create Provider Base Classes and Registry | NXP-28 |
| NXP-32 | Implement AWS Bedrock Provider | NXP-28 |
| NXP-33 | Implement OpenAI Provider | NXP-28 |
| NXP-34 | Implement Ollama Provider | NXP-28 |
| NXP-35 | Create Provider API Endpoints | NXP-28 |

## Key Outputs

- `backend/src/nexuspkm/config/` — Pydantic settings, YAML + env var loader
- `backend/src/nexuspkm/models/` — Document, Entity, Relationship, Search, Chat models
- `backend/src/nexuspkm/providers/` — BaseLLMProvider, BaseEmbeddingProvider, registry, Bedrock/OpenAI/Ollama implementations
- `GET /api/providers/health`, `GET /api/providers/active`, `PUT /api/providers/config`

## Parallelization

NXP-26 and NXP-27 can be worked in parallel. NXP-28 depends on NXP-26.
