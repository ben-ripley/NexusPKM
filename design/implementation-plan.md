# NexusPKM Implementation Plan

**Version:** 1.0
**Date:** 2026-03-16

This document defines all Jira issues in Epic > Story > SubTask hierarchy, ordered by dependency and implementation phase. Each issue is detailed enough for a Claude Code agent to implement independently.

---

## Dependency Graph (Epic Level)

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

## EPIC 1: Project Infrastructure & DevOps Setup

**Description:** Set up the development environment, repository, CI/CD, and project management tooling.
**Labels:** `infrastructure`, `devops`
**Phase:** 0 — Prerequisites

---

### Story 1.1: Configure Development Environment

**Description:** Configure Claude Code settings.json, install MCP plugins and LSPs, and set up the local development environment for autonomous operation.
**Complexity:** S
**Dependencies:** None
**Labels:** `infrastructure`, `tooling`
**Acceptance Criteria:**
- [ ] Claude Code settings.json configured with appropriate permissions for autonomous operation
- [ ] Required MCP plugins installed and configured
- [ ] Python LSP (pyright/pylance) configured for backend
- [ ] TypeScript LSP configured for frontend
- [ ] CLAUDE.md file created with project conventions

#### SubTask 1.1.1: Create Claude Code Settings
**Description:** Create `.claude/settings.json` in the project root with permissions configured for autonomous development. Include allowed commands (git, npm, pip, pytest, etc.), MCP server configurations, and tool permissions.
**Files:** `.claude/settings.json`
**Acceptance Criteria:**
- [ ] settings.json allows running git, npm, npx, pip, poetry, pytest, ruff, mypy commands without approval
- [ ] settings.json allows read/write to all project directories
- [ ] MCP plugins configured (context7 for documentation lookups)

#### SubTask 1.1.2: Create CLAUDE.md Project Guide
**Description:** Create a `CLAUDE.md` file in the repo root that serves as the project convention guide for Claude Code agents. Include: project structure, coding conventions, test patterns, commit message format, branch naming, spec references.
**Files:** `CLAUDE.md`
**Acceptance Criteria:**
- [ ] CLAUDE.md documents project structure and conventions
- [ ] References design/specs/ for feature implementation
- [ ] Includes coding style guidelines (ruff config, TypeScript conventions)

---

### Story 1.2: Create GitHub Repository

**Description:** Create the GitHub repository with branch protection, PR templates, and issue templates.
**Complexity:** S
**Dependencies:** None
**Labels:** `infrastructure`, `github`
**Acceptance Criteria:**
- [ ] Repository created at appropriate GitHub org/account
- [ ] Branch protection on `main`: require PR, require CI pass
- [ ] PR template created
- [ ] .gitignore configured for Python + Node.js + project-specific exclusions

#### SubTask 1.2.1: Initialize Repository and Monorepo Structure
**Description:** Create the GitHub repo and initialize the monorepo directory structure as defined in ADR-003.
**Files:**
```
.gitignore
README.md
LICENSE
.github/PULL_REQUEST_TEMPLATE.md
backend/README.md
frontend/README.md
config/providers.yaml.example
config/connectors.yaml.example
config/app.yaml.example
```
**Acceptance Criteria:**
- [ ] Repo initialized with all top-level directories
- [ ] .gitignore includes: data/, config/*.yaml (not .example), .tokens/, __pycache__, node_modules/, .env, *.pyc
- [ ] README.md includes project overview and setup instructions
- [ ] PR template includes Summary, Spec Reference, Test Plan, Checklist sections

#### SubTask 1.2.2: Configure Branch Protection
**Description:** Set up branch protection rules on `main` via GitHub CLI or API.
**Commands:** `gh api repos/{owner}/{repo}/branches/main/protection`
**Acceptance Criteria:**
- [ ] Direct push to main is blocked
- [ ] PRs require at least 1 approval (can be relaxed later for autonomous flow)
- [ ] Status checks required: CI pipeline must pass

---

### Story 1.3: Set Up Python Backend Project

**Description:** Initialize the Python backend project with FastAPI, dependency management, linting, type checking, and test configuration.
**Complexity:** M
**Dependencies:** Story 1.2
**Labels:** `infrastructure`, `backend`
**Spec Reference:** ADR-006

#### SubTask 1.3.1: Initialize Python Project with uv
**Description:** Set up the Python project using `uv` (fast Python package manager). Create pyproject.toml with project metadata, dependencies, and tool configuration.
**Files:**
```
backend/pyproject.toml
backend/src/nexuspkm/__init__.py
backend/src/nexuspkm/main.py        # FastAPI app skeleton
backend/tests/__init__.py
backend/tests/conftest.py
```
**Dependencies:**
```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.0
pydantic-settings>=2.0
pyyaml>=6.0
structlog>=24.0
apscheduler>=3.10
httpx>=0.27.0
```
**Dev Dependencies:**
```
pytest>=8.0
pytest-asyncio>=0.24
pytest-cov>=5.0
ruff>=0.6.0
mypy>=1.11
```
**Acceptance Criteria:**
- [ ] `uv sync` installs all dependencies
- [ ] `uvicorn nexuspkm.main:app` starts the server
- [ ] `GET /health` returns `{"status": "ok"}`
- [ ] `pytest` runs with 0 errors (empty test suite)

#### SubTask 1.3.2: Configure Linting and Type Checking
**Description:** Configure ruff (linter + formatter) and mypy (type checker) in pyproject.toml.
**Files:** `backend/pyproject.toml` (update tool sections)
**Acceptance Criteria:**
- [ ] `ruff check .` passes with zero errors
- [ ] `ruff format --check .` passes
- [ ] `mypy src/` passes with zero errors
- [ ] Rules configured: ruff (I, E, W, F, UP, B, SIM, PT), mypy strict mode

---

### Story 1.4: Set Up Frontend Project

**Description:** Initialize the React + TypeScript + Tailwind + Vite frontend project.
**Complexity:** M
**Dependencies:** Story 1.2
**Labels:** `infrastructure`, `frontend`
**Spec Reference:** ADR-005

#### SubTask 1.4.1: Initialize Vite + React + TypeScript Project
**Description:** Create the frontend project using Vite with React and TypeScript template. Install and configure Tailwind CSS and shadcn/ui.
**Files:**
```
frontend/package.json
frontend/vite.config.ts
frontend/tsconfig.json
frontend/tailwind.config.ts
frontend/postcss.config.js
frontend/src/main.tsx
frontend/src/App.tsx
frontend/src/index.css
frontend/components.json         # shadcn/ui config
```
**Commands:**
```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm install tailwindcss @tailwindcss/vite
npx shadcn@latest init
npm install zustand @tanstack/react-query react-router-dom lucide-react
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```
**Acceptance Criteria:**
- [ ] `npm run dev` starts the dev server
- [ ] `npm run build` produces production build
- [ ] Tailwind utilities render correctly
- [ ] shadcn/ui Button component works
- [ ] `npx vitest run` passes (empty test suite)
- [ ] Dark mode class strategy configured

---

### Story 1.5: Create CI/CD Pipeline

**Description:** Set up GitHub Actions for automated testing and the custom AI PR review.
**Complexity:** M
**Dependencies:** Story 1.3, Story 1.4
**Labels:** `infrastructure`, `cicd`
**Spec Reference:** ADR-008

#### SubTask 1.5.1: Create CI Workflow
**Description:** Create `.github/workflows/ci.yml` that runs on every PR: backend lint + type check + test, frontend lint + type check + test + build.
**Files:** `.github/workflows/ci.yml`
**Acceptance Criteria:**
- [ ] Workflow triggers on PR to main
- [ ] Backend: ruff check, mypy, pytest with coverage
- [ ] Frontend: eslint, tsc --noEmit, vitest, vite build
- [ ] All checks must pass for PR to be mergeable

#### SubTask 1.5.2: Create AI Review GitHub Action
**Description:** Create a custom GitHub Action that uses the Claude API to review PR diffs for architecture compliance, security issues, bugs, test coverage, and spec adherence. Post findings as a PR comment.
**Files:**
```
.github/workflows/ai-review.yml
scripts/ai_review.py
```
**Acceptance Criteria:**
- [ ] Action triggers on PR open and synchronize
- [ ] Fetches PR diff and sends to Claude API
- [ ] Posts structured review comment (critical/warning/info findings)
- [ ] Uses ANTHROPIC_API_KEY from GitHub secrets
- [ ] Handles large diffs gracefully (truncate if needed)

---

### Story 1.6: Set Up Jira Project

**Description:** Create and configure the Jira project with appropriate workflows, issue types, and labels.
**Complexity:** S
**Dependencies:** None
**Labels:** `infrastructure`, `project-management`

#### SubTask 1.6.1: Create Jira Project and Configure
**Description:** Create the NXP Jira project. Configure: issue types (Epic, Story, SubTask), workflow (To Do → In Progress → In Review → Done → Blocked), labels (infrastructure, backend, frontend, connector, engine, etc.), components (backend, frontend, connectors, engine, devops).
**Acceptance Criteria:**
- [ ] Jira project NXP created
- [ ] Issue types: Epic, Story, Sub-task
- [ ] Workflow states: To Do, In Progress, In Review, Done, Blocked
- [ ] Labels created for all categories
- [ ] Components match project structure

---

## EPIC 2: Core Backend Architecture

**Description:** Implement foundational backend components: LLM provider abstraction, configuration system, and common data models.
**Labels:** `backend`, `core`
**Phase:** 1 — Foundation
**Dependencies:** Epic 1

---

### Story 2.1: Implement Configuration Management System

**Description:** Build the YAML + environment variable configuration system for the application.
**Complexity:** M
**Dependencies:** Story 1.3
**Labels:** `backend`, `core`
**Spec Reference:** F-001 (configuration section), Architecture doc (section 6)

#### SubTask 2.1.1: Create Configuration Models
**Description:** Create Pydantic settings models for all application configuration: providers, connectors, app settings. Support YAML file loading with environment variable overrides.
**Files:**
```
backend/src/nexuspkm/config/__init__.py
backend/src/nexuspkm/config/models.py      # Pydantic config models
backend/src/nexuspkm/config/loader.py       # YAML + env var loading
backend/tests/unit/test_config.py
```
**Test Requirements:**
- Valid YAML config loads correctly
- Missing required fields raise validation errors
- Environment variables override YAML values
- Default values apply when not specified
- Secrets (API keys) only from env vars
**Acceptance Criteria:**
- [ ] Configuration loads from YAML files in config/ directory
- [ ] Environment variables override YAML values
- [ ] Validation errors are clear and actionable
- [ ] All tests pass

---

### Story 2.2: Implement Common Data Models

**Description:** Create the shared Pydantic data models used across the application: Document, Entity, Relationship, etc.
**Complexity:** M
**Dependencies:** Story 2.1
**Labels:** `backend`, `core`
**Spec Reference:** F-002 (data model section)

#### SubTask 2.2.1: Create Document and Metadata Models
**Description:** Implement the common Document schema, DocumentMetadata, SourceType enum, and all shared data models referenced across feature specs.
**Files:**
```
backend/src/nexuspkm/models/__init__.py
backend/src/nexuspkm/models/document.py
backend/src/nexuspkm/models/entity.py
backend/src/nexuspkm/models/relationship.py
backend/src/nexuspkm/models/search.py
backend/src/nexuspkm/models/chat.py
backend/tests/unit/test_models.py
```
**Test Requirements:**
- All models validate correctly with valid data
- Invalid data raises appropriate ValidationErrors
- Serialization/deserialization roundtrip works
- Optional fields handle None correctly
**Acceptance Criteria:**
- [ ] All models from F-002, F-005, F-006, F-007 data model sections are implemented
- [ ] Models serialize to/from JSON correctly
- [ ] All tests pass

---

### Story 2.3: Implement LLM Provider Abstraction Layer

**Description:** Build the configurable LLM and embedding provider system with health checks and fallback support.
**Complexity:** L
**Dependencies:** Story 2.1
**Labels:** `backend`, `core`, `llm`
**Spec Reference:** F-001

#### SubTask 2.3.1: Create Provider Base Classes and Registry
**Description:** Implement BaseLLMProvider, BaseEmbeddingProvider abstract classes and the ProviderRegistry that manages provider lifecycle.
**Files:**
```
backend/src/nexuspkm/providers/__init__.py
backend/src/nexuspkm/providers/base.py        # Abstract base classes
backend/src/nexuspkm/providers/registry.py     # Provider registry + fallback
backend/src/nexuspkm/providers/models.py       # LLMResponse, EmbeddingResponse, ProviderHealth
backend/tests/unit/test_provider_registry.py
```
**Test Requirements:**
- Registry loads providers from config
- Fallback activates when primary fails
- Health check aggregates all provider statuses
- Invalid provider config raises errors
**Acceptance Criteria:**
- [ ] Base classes define the complete provider interface
- [ ] Registry instantiates providers from configuration
- [ ] Fallback chain works (primary fails → fallback activates)
- [ ] Health check returns status for all configured providers

#### SubTask 2.3.2: Implement AWS Bedrock Provider
**Description:** Implement the AWS Bedrock LLM and embedding provider using llama-index-llms-bedrock and llama-index-embeddings-bedrock.
**Files:**
```
backend/src/nexuspkm/providers/bedrock.py
backend/tests/unit/test_provider_bedrock.py
```
**Dependencies:** SubTask 2.3.1
**Test Requirements:**
- Mock boto3 client for unit tests
- Test generate, stream, embed, embed_single methods
- Test health check with mocked API
- Test error handling (auth failure, rate limit, timeout)
**Acceptance Criteria:**
- [ ] LLM generate and stream work with mocked Bedrock API
- [ ] Embedding generation works with mocked Bedrock API
- [ ] Health check validates connectivity
- [ ] Error handling for common failure modes

#### SubTask 2.3.3: Implement OpenAI Provider
**Description:** Implement OpenAI LLM and embedding provider. This also serves as the base for OpenRouter and LM Studio (OpenAI-compatible endpoints).
**Files:**
```
backend/src/nexuspkm/providers/openai.py
backend/tests/unit/test_provider_openai.py
```
**Dependencies:** SubTask 2.3.1
**Acceptance Criteria:**
- [ ] LLM and embedding methods work with mocked OpenAI API
- [ ] Supports custom base_url for OpenRouter/LM Studio
- [ ] Health check validates connectivity

#### SubTask 2.3.4: Implement Ollama Provider
**Description:** Implement Ollama LLM and embedding provider for local model support.
**Files:**
```
backend/src/nexuspkm/providers/ollama.py
backend/tests/unit/test_provider_ollama.py
```
**Dependencies:** SubTask 2.3.1
**Acceptance Criteria:**
- [ ] LLM and embedding methods work with mocked Ollama API
- [ ] Health check validates local Ollama is running
- [ ] Graceful error when Ollama is not available

#### SubTask 2.3.5: Create Provider API Endpoints
**Description:** Implement FastAPI endpoints for provider health, active provider info, and config hot-reload.
**Files:**
```
backend/src/nexuspkm/api/providers.py
backend/tests/integration/test_api_providers.py
```
**Dependencies:** SubTask 2.3.1
**Acceptance Criteria:**
- [ ] GET /api/providers/health returns all provider statuses
- [ ] GET /api/providers/active returns current active providers
- [ ] PUT /api/providers/config updates config without restart

---

## EPIC 3: Knowledge Engine

**Description:** Set up the hybrid vector + graph knowledge engine with LlamaIndex orchestration.
**Labels:** `backend`, `engine`
**Phase:** 2 — Core Engine
**Dependencies:** Epic 2

---

### Story 3.1: Set Up LanceDB Vector Store

**Description:** Initialize and configure LanceDB for vector storage with the document schema.
**Complexity:** M
**Dependencies:** Story 2.2, Story 2.3
**Labels:** `backend`, `engine`
**Spec Reference:** F-002 (FR-3)

#### SubTask 3.1.1: Initialize LanceDB and Implement Vector Operations
**Description:** Set up LanceDB database, create the documents table with the correct schema, implement store, search, and delete operations.
**Files:**
```
backend/src/nexuspkm/engine/__init__.py
backend/src/nexuspkm/engine/vector_store.py
backend/tests/unit/test_vector_store.py
backend/tests/integration/test_vector_store_integration.py
```
**Test Requirements:**
- Store vectors and retrieve by similarity
- Metadata filtering (source_type, date range)
- Delete by document ID
- Handle empty database gracefully
**Acceptance Criteria:**
- [ ] Vectors stored and persisted to data/lancedb/
- [ ] Cosine similarity search returns ranked results
- [ ] Metadata filtering works correctly
- [ ] Database survives application restart

---

### Story 3.2: Set Up Kuzu Graph Database

**Description:** Initialize Kuzu with the entity/relationship schema defined in F-002.
**Complexity:** M
**Dependencies:** Story 2.2
**Labels:** `backend`, `engine`
**Spec Reference:** F-002 (FR-4)

#### SubTask 3.2.1: Initialize Kuzu and Create Schema
**Description:** Set up Kuzu database, create all node tables (Person, Project, Topic, Decision, ActionItem, Meeting, Document) and relationship tables as defined in F-002 FR-4.
**Files:**
```
backend/src/nexuspkm/engine/graph_store.py
backend/tests/unit/test_graph_store.py
backend/tests/integration/test_graph_store_integration.py
```
**Test Requirements:**
- Create/read/update/delete entities
- Create/read relationships
- Cypher queries return correct results
- Schema migration on startup (idempotent)
**Acceptance Criteria:**
- [ ] All node and relationship tables created
- [ ] CRUD operations work for all entity types
- [ ] Cypher queries return correct traversal results
- [ ] Database persists to data/kuzu/

---

### Story 3.3: Integrate LlamaIndex PropertyGraphIndex

**Description:** Connect LlamaIndex's PropertyGraphIndex to Kuzu and LanceDB backends.
**Complexity:** L
**Dependencies:** Story 3.1, Story 3.2, Story 2.3
**Labels:** `backend`, `engine`
**Spec Reference:** F-002 (FR-2, FR-5)

#### SubTask 3.3.1: Configure PropertyGraphIndex with Dual Backends
**Description:** Set up LlamaIndex PropertyGraphIndex using KuzuPropertyGraphStore and LanceDB as the vector store. Configure entity/relationship extraction prompts.
**Files:**
```
backend/src/nexuspkm/engine/index.py
backend/tests/integration/test_index_integration.py
```
**Acceptance Criteria:**
- [ ] PropertyGraphIndex initializes with Kuzu + LanceDB
- [ ] Document insertion triggers both vector storage and graph extraction
- [ ] Hybrid retrieval returns combined vector + graph results

#### SubTask 3.3.2: Implement Document Ingestion Pipeline
**Description:** Build the full ingestion pipeline: receive Document → chunk → embed → store in LanceDB → extract entities → store in Kuzu. Include chunking configuration and async processing.
**Files:**
```
backend/src/nexuspkm/engine/ingestion.py
backend/src/nexuspkm/engine/chunking.py
backend/tests/unit/test_chunking.py
backend/tests/integration/test_ingestion_pipeline.py
```
**Test Requirements:**
- Documents chunked correctly (size, overlap)
- Chunks embedded and stored in LanceDB
- Entities extracted and stored in Kuzu
- Pipeline is idempotent
- Handles errors without partial writes
**Acceptance Criteria:**
- [ ] Full pipeline processes a document end-to-end
- [ ] Chunking respects configured size and overlap
- [ ] Vectors stored in LanceDB with correct metadata
- [ ] Entities/relationships stored in Kuzu
- [ ] Re-processing same document produces same result

#### SubTask 3.3.3: Implement Hybrid Retrieval
**Description:** Build the hybrid retrieval function that combines vector similarity search with graph traversal, merges results, and ranks by combined score.
**Files:**
```
backend/src/nexuspkm/engine/retrieval.py
backend/tests/unit/test_retrieval.py
backend/tests/integration/test_retrieval_integration.py
```
**Test Requirements:**
- Vector search returns semantically similar chunks
- Graph traversal returns connected entities/documents
- Results merged without duplicates
- Ranking formula produces expected ordering
**Acceptance Criteria:**
- [ ] Hybrid retrieval combines vector + graph results
- [ ] Combined scoring formula works as specified
- [ ] Source attribution included in results
- [ ] Performance < 500ms for test dataset

---

### Story 3.4: Implement Engine API Endpoints

**Description:** Create the REST API endpoints for the knowledge engine.
**Complexity:** S
**Dependencies:** Story 3.3
**Labels:** `backend`, `engine`, `api`
**Spec Reference:** F-002 (API section)

#### SubTask 3.4.1: Create Engine REST Endpoints
**Description:** Implement POST /api/engine/ingest, POST /api/engine/reindex, GET /api/engine/stats, GET /api/engine/status.
**Files:**
```
backend/src/nexuspkm/api/engine.py
backend/tests/integration/test_api_engine.py
```
**Acceptance Criteria:**
- [ ] Ingest endpoint accepts Document and triggers pipeline
- [ ] Stats endpoint returns document/entity/relationship counts
- [ ] Status endpoint returns pipeline processing status
- [ ] Reindex endpoint triggers re-indexing

---

## EPIC 4: Connector Framework & V1 Connectors

**Description:** Build the pluggable connector framework and implement Teams + Obsidian connectors.
**Labels:** `backend`, `connector`
**Phase:** 3 — Data Ingestion
**Dependencies:** Epic 3

---

### Story 4.1: Implement Connector Framework

**Description:** Build the BaseConnector abstract class, connector registry, and sync scheduler.
**Complexity:** M
**Dependencies:** Story 3.3
**Labels:** `backend`, `connector`, `core`
**Spec Reference:** ADR-004

#### SubTask 4.1.1: Create BaseConnector and Registry
**Description:** Implement the BaseConnector abstract class, ConnectorRegistry, ConnectorStatus model, and the configuration-driven connector loading system.
**Files:**
```
backend/src/nexuspkm/connectors/__init__.py
backend/src/nexuspkm/connectors/base.py
backend/src/nexuspkm/connectors/registry.py
backend/tests/unit/test_connector_registry.py
```
**Acceptance Criteria:**
- [ ] BaseConnector defines authenticate, fetch, health_check, sync state interface
- [ ] Registry loads enabled connectors from config
- [ ] Registry exposes connector status for all registered connectors
- [ ] Disabled connectors are not instantiated

#### SubTask 4.1.2: Implement Sync Scheduler
**Description:** Build the background sync scheduler using APScheduler that periodically triggers connector syncs based on configured intervals.
**Files:**
```
backend/src/nexuspkm/connectors/scheduler.py
backend/tests/unit/test_sync_scheduler.py
```
**Acceptance Criteria:**
- [ ] Scheduler triggers connector.fetch() at configured intervals
- [ ] Sync results are fed into the ingestion pipeline
- [ ] Failed syncs are logged and retried on next interval
- [ ] Connector status updated after each sync

---

### Story 4.2: Implement Microsoft Graph Authentication

**Description:** Build the shared OAuth2 authentication module for Microsoft Graph API (used by Teams and Outlook connectors).
**Complexity:** M
**Dependencies:** Story 4.1
**Labels:** `backend`, `connector`, `microsoft`
**Spec Reference:** F-003 (FR-1)

#### SubTask 4.2.1: Implement Device Code OAuth2 Flow
**Description:** Build the Microsoft Graph OAuth2 authentication using device code flow. Handle token storage, refresh, and re-authentication.
**Files:**
```
backend/src/nexuspkm/connectors/microsoft/auth.py
backend/tests/unit/test_ms_auth.py
```
**Test Requirements:**
- Mock OAuth2 token responses
- Test token refresh logic
- Test token storage/retrieval
- Test expired token handling
**Acceptance Criteria:**
- [ ] Device code flow initiates and completes authentication
- [ ] Tokens stored encrypted at data/.tokens/ms_graph.json
- [ ] Token refresh happens automatically before expiry
- [ ] Clear error message when re-authentication needed

---

### Story 4.3: Implement Teams Transcript Connector

**Description:** Build the connector that ingests meeting transcripts from Microsoft Teams.
**Complexity:** L
**Dependencies:** Story 4.2
**Labels:** `backend`, `connector`, `microsoft`, `v1`
**Spec Reference:** F-003

#### SubTask 4.3.1: Implement Meeting Discovery
**Description:** Query Microsoft Graph API to discover meetings with available transcripts. Handle pagination and filtering.
**Files:**
```
backend/src/nexuspkm/connectors/microsoft/teams.py
backend/tests/unit/test_teams_connector.py
```
**Acceptance Criteria:**
- [ ] Discovers meetings via GET /me/onlineMeetings
- [ ] Filters for meetings with transcripts
- [ ] Supports incremental discovery (since timestamp)
- [ ] Handles pagination

#### SubTask 4.3.2: Implement VTT Transcript Parsing
**Description:** Parse VTT-format transcripts into structured segments with speaker attribution.
**Files:**
```
backend/src/nexuspkm/connectors/microsoft/vtt_parser.py
backend/tests/unit/test_vtt_parser.py
backend/tests/fixtures/sample_transcript.vtt
```
**Test Requirements:**
- Parse valid VTT with multiple speakers
- Handle malformed VTT gracefully
- Handle empty transcripts
- Extract correct speaker-to-text mapping
**Acceptance Criteria:**
- [ ] VTT parsed into TranscriptSegments with speaker, time, text
- [ ] Full text generated with speaker labels
- [ ] Malformed/empty VTT handled without crash

#### SubTask 4.3.3: Implement Document Transformation and Sync
**Description:** Transform parsed transcripts into common Document schema and implement the full sync flow (discover → fetch → parse → transform → ingest).
**Files:** Update `backend/src/nexuspkm/connectors/microsoft/teams.py`
**Acceptance Criteria:**
- [ ] ParsedTranscript transforms to Document correctly
- [ ] Full sync flow works end-to-end (with mocked API)
- [ ] Incremental sync only fetches new transcripts
- [ ] Rate limiting handles 429 responses

---

### Story 4.4: Implement Obsidian Notes Connector

**Description:** Build the connector that ingests markdown notes from an Obsidian vault.
**Complexity:** L
**Dependencies:** Story 4.1
**Labels:** `backend`, `connector`, `v1`
**Spec Reference:** F-004

#### SubTask 4.4.1: Implement Markdown Parser
**Description:** Parse Obsidian markdown files: extract YAML frontmatter, wikilinks, tags, embeds, and plain text content.
**Files:**
```
backend/src/nexuspkm/connectors/obsidian/parser.py
backend/tests/unit/test_obsidian_parser.py
backend/tests/fixtures/obsidian_vault/          # Sample vault
```
**Test Requirements:**
- Parse frontmatter correctly
- Extract [[wikilinks]] and [[link|display text]]
- Extract #tags and #nested/tags
- Extract ![[embeds]]
- Handle files without frontmatter
- Handle empty files
**Acceptance Criteria:**
- [ ] Frontmatter parsed into dict
- [ ] All Obsidian syntax elements extracted
- [ ] Plain text version generated for embedding

#### SubTask 4.4.2: Implement Filesystem Watcher
**Description:** Set up filesystem watching using `watchfiles` for real-time change detection. Include initial full scan, debouncing, and exclude pattern support.
**Files:**
```
backend/src/nexuspkm/connectors/obsidian/watcher.py
backend/src/nexuspkm/connectors/obsidian/connector.py
backend/tests/unit/test_obsidian_watcher.py
backend/tests/integration/test_obsidian_connector.py
```
**Acceptance Criteria:**
- [ ] Full vault scan discovers all .md files respecting excludes
- [ ] Real-time watcher detects create/modify/delete
- [ ] Debounce prevents redundant processing
- [ ] Deleted files trigger removal from knowledge base

---

### Story 4.5: Implement Connector API Endpoints

**Description:** Create REST API endpoints for connector management.
**Complexity:** S
**Dependencies:** Story 4.1
**Labels:** `backend`, `connector`, `api`

#### SubTask 4.5.1: Create Connector REST Endpoints
**Description:** Implement endpoints for connector status, manual sync trigger, and config updates. Generic endpoints that work with any registered connector.
**Files:**
```
backend/src/nexuspkm/api/connectors.py
backend/tests/integration/test_api_connectors.py
```
**Acceptance Criteria:**
- [ ] GET /api/connectors/status returns all connector statuses
- [ ] POST /api/connectors/{name}/sync triggers manual sync
- [ ] PUT /api/connectors/{name}/config updates connector settings
- [ ] POST /api/connectors/{name}/authenticate initiates auth flow (for MS connectors)

---

## EPIC 5: Entity & Relationship Intelligence

**Description:** Build the entity extraction, deduplication, and contradiction detection pipeline.
**Labels:** `backend`, `intelligence`
**Phase:** 4 — Intelligence
**Dependencies:** Epic 3, Epic 4

---

### Story 5.1: Implement Entity Extraction Pipeline

**Description:** Build the LLM-powered entity and relationship extraction system.
**Complexity:** L
**Dependencies:** Story 3.3, Story 4.3 or 4.4 (needs documents to extract from)
**Labels:** `backend`, `intelligence`
**Spec Reference:** F-006

#### SubTask 5.1.1: Create Extraction Prompts and Parser
**Description:** Design the LLM extraction prompt and implement the structured JSON response parser for entities and relationships.
**Files:**
```
backend/src/nexuspkm/intelligence/__init__.py
backend/src/nexuspkm/intelligence/extraction.py
backend/src/nexuspkm/intelligence/prompts.py
backend/tests/unit/test_extraction.py
```
**Acceptance Criteria:**
- [ ] LLM prompt extracts Person, Project, Topic, Decision, ActionItem entities
- [ ] Relationships between entities are extracted
- [ ] JSON response parser handles valid and malformed LLM output
- [ ] Confidence scores assigned to each extraction

#### SubTask 5.1.2: Implement Entity Deduplication
**Description:** Build the entity resolution system: name matching, email matching, alias tracking, LLM-assisted disambiguation.
**Files:**
```
backend/src/nexuspkm/intelligence/deduplication.py
backend/tests/unit/test_deduplication.py
```
**Acceptance Criteria:**
- [ ] Exact name match resolves correctly
- [ ] Email match resolves correctly
- [ ] Fuzzy name match (Levenshtein) works within threshold
- [ ] Aliases are tracked and stored

#### SubTask 5.1.3: Implement Contradiction Detection
**Description:** Detect when new information conflicts with existing knowledge and create flagged records.
**Files:**
```
backend/src/nexuspkm/intelligence/contradictions.py
backend/tests/unit/test_contradictions.py
```
**Acceptance Criteria:**
- [ ] Date/deadline conflicts detected
- [ ] Status conflicts detected
- [ ] Contradictions stored with both values and source references
- [ ] Auto-resolution by recency works (configurable)

#### SubTask 5.1.4: Implement Background Extraction Queue
**Description:** Build the async extraction queue that processes documents after ingestion.
**Files:**
```
backend/src/nexuspkm/intelligence/queue.py
backend/tests/unit/test_extraction_queue.py
```
**Acceptance Criteria:**
- [ ] Queue persists across application restarts
- [ ] Documents processed FIFO
- [ ] Configurable concurrency
- [ ] Failed extractions retried with backoff

---

### Story 5.2: Implement Entity API Endpoints

**Description:** Create REST API for browsing and managing entities and relationships.
**Complexity:** M
**Dependencies:** Story 5.1
**Labels:** `backend`, `intelligence`, `api`
**Spec Reference:** F-006 (API section)

#### SubTask 5.2.1: Create Entity and Relationship Endpoints
**Description:** Implement the entity CRUD, relationship browsing, entity merge, contradiction management endpoints.
**Files:**
```
backend/src/nexuspkm/api/entities.py
backend/tests/integration/test_api_entities.py
```
**Acceptance Criteria:**
- [ ] GET /api/entities lists entities with type/name filtering
- [ ] GET /api/entities/{id} returns entity with relationships
- [ ] POST /api/entities/merge merges two entities
- [ ] GET /api/contradictions lists flagged contradictions
- [ ] POST /api/contradictions/{id}/resolve resolves a contradiction

---

## EPIC 6: Frontend Core

**Description:** Build the web UI: application shell, chat interface, search, dashboard, and graph explorer.
**Labels:** `frontend`
**Phase:** 5 — User Interface
**Dependencies:** Epic 3, Epic 5 (for API endpoints)

---

### Story 6.1: Implement Application Shell

**Description:** Build the top-level layout, navigation, routing, and theme system.
**Complexity:** M
**Dependencies:** Story 1.4
**Labels:** `frontend`, `core`
**Spec Reference:** F-008 (FR-1, FR-3)

#### SubTask 6.1.1: Create Layout, Routing, and Theme
**Description:** Implement the application shell with sidebar navigation, top bar, routing between pages, and dark/light theme toggle. Use shadcn/ui components.
**Files:**
```
frontend/src/App.tsx
frontend/src/components/layout/AppShell.tsx
frontend/src/components/layout/Sidebar.tsx
frontend/src/components/layout/TopBar.tsx
frontend/src/components/ui/theme-toggle.tsx
frontend/src/pages/Dashboard.tsx          # Placeholder
frontend/src/pages/Chat.tsx               # Placeholder
frontend/src/pages/Search.tsx             # Placeholder
frontend/src/pages/GraphExplorer.tsx      # Placeholder
frontend/src/pages/Settings.tsx           # Placeholder
frontend/src/stores/theme.ts
frontend/tests/AppShell.test.tsx
```
**Acceptance Criteria:**
- [ ] Sidebar with navigation links renders
- [ ] Routing between all 5 pages works
- [ ] Dark/light theme toggle works and persists in localStorage
- [ ] Top bar with logo, global search, and theme toggle renders
- [ ] Responsive: sidebar collapses on smaller screens

---

### Story 6.2: Implement Chat Interface

**Description:** Build the real-time chat UI with WebSocket, streaming responses, and source citations.
**Complexity:** XL
**Dependencies:** Story 6.1, Story 3.3 (hybrid retrieval), Story 2.3 (LLM provider)
**Labels:** `frontend`, `chat`
**Spec Reference:** F-005

#### SubTask 6.2.1: Create Chat WebSocket Backend
**Description:** Implement the FastAPI WebSocket endpoint for chat with streaming LLM responses, hybrid retrieval context, and source attribution.
**Files:**
```
backend/src/nexuspkm/api/chat.py
backend/src/nexuspkm/services/chat.py
backend/tests/integration/test_api_chat.py
```
**Acceptance Criteria:**
- [ ] WebSocket endpoint accepts queries and streams responses
- [ ] Hybrid retrieval provides context for LLM generation
- [ ] Source attribution sent after response completion
- [ ] Session management (create, list, delete)

#### SubTask 6.2.2: Create Chat UI Components
**Description:** Build the chat page with message list, input area, source cards, and session sidebar. Use the frontend-design skill for a polished interface.
**Files:**
```
frontend/src/pages/Chat.tsx
frontend/src/components/chat/ChatMessageList.tsx
frontend/src/components/chat/ChatInput.tsx
frontend/src/components/chat/ChatMessage.tsx
frontend/src/components/chat/SourceCard.tsx
frontend/src/components/chat/SessionList.tsx
frontend/src/hooks/useChat.ts
frontend/src/services/websocket.ts
frontend/tests/Chat.test.tsx
```
**Acceptance Criteria:**
- [ ] Messages render with markdown support
- [ ] Streaming responses display token-by-token
- [ ] Source cards appear below assistant messages
- [ ] Session list in sidebar, switchable
- [ ] Input supports Enter to send, Shift+Enter for newline
- [ ] WebSocket reconnects on disconnection
- [ ] Follow-up suggestions appear after responses

---

### Story 6.3: Implement Search Interface

**Description:** Build the search page with search bar, results, and faceted filtering.
**Complexity:** L
**Dependencies:** Story 6.1, Story 3.4 (engine API)
**Labels:** `frontend`, `search`
**Spec Reference:** F-007

#### SubTask 6.3.1: Create Search UI Components
**Description:** Build the search page: search bar with autocomplete, results list with source badges and excerpts, filter sidebar with facets.
**Files:**
```
frontend/src/pages/Search.tsx
frontend/src/components/search/SearchBar.tsx
frontend/src/components/search/SearchResults.tsx
frontend/src/components/search/SearchFilters.tsx
frontend/src/components/search/ResultCard.tsx
frontend/src/hooks/useSearch.ts
frontend/src/services/api.ts              # API client
frontend/tests/Search.test.tsx
```
**Acceptance Criteria:**
- [ ] Search bar with autocomplete suggestions
- [ ] Results list with title, excerpt, source badge, timestamp
- [ ] Filter sidebar: source type, date range, tags
- [ ] Filters update results in real-time
- [ ] Empty state and loading state handled

---

### Story 6.4: Implement Dashboard

**Description:** Build the dashboard home page with activity feed, connector status, stats, and graph mini-view.
**Complexity:** L
**Dependencies:** Story 6.1, Story 3.4, Story 4.5
**Labels:** `frontend`, `dashboard`
**Spec Reference:** F-008

#### SubTask 6.4.1: Create Dashboard Components
**Description:** Build all dashboard panels: activity feed, connector status cards, knowledge base stats, quick search, and mini graph view. Use the frontend-design skill for a polished layout.
**Files:**
```
frontend/src/pages/Dashboard.tsx
frontend/src/components/dashboard/ActivityFeed.tsx
frontend/src/components/dashboard/ConnectorStatusPanel.tsx
frontend/src/components/dashboard/KnowledgeBaseStats.tsx
frontend/src/components/dashboard/MiniGraphView.tsx
frontend/src/hooks/useDashboard.ts
frontend/tests/Dashboard.test.tsx
```
**Acceptance Criteria:**
- [ ] Activity feed shows recent changes
- [ ] Connector cards show status, last sync, document count
- [ ] Stats panel shows document/entity/relationship counts
- [ ] Quick search works from dashboard
- [ ] Mini graph renders top entities

---

### Story 6.5: Implement Graph Explorer

**Description:** Build the interactive knowledge graph visualization page.
**Complexity:** L
**Dependencies:** Story 6.1, Story 5.2 (entity API)
**Labels:** `frontend`, `graph`
**Spec Reference:** F-008 (graph section)

#### SubTask 6.5.1: Create Graph Visualization
**Description:** Build an interactive, zoomable knowledge graph using react-force-graph or D3.js. Support entity filtering, click-to-explore, and relationship highlighting.
**Files:**
```
frontend/src/pages/GraphExplorer.tsx
frontend/src/components/graph/GraphCanvas.tsx
frontend/src/components/graph/GraphControls.tsx
frontend/src/components/graph/EntityDetail.tsx
frontend/src/hooks/useGraphData.ts
frontend/tests/GraphExplorer.test.tsx
```
**Acceptance Criteria:**
- [ ] Force-directed graph renders entities and relationships
- [ ] Zoom, pan, and drag interactions work
- [ ] Click entity to see details and connected entities
- [ ] Filter by entity type
- [ ] Performance acceptable with 1000+ nodes

---

### Story 6.6: Implement Settings Page

**Description:** Build the settings page for provider config, connector management, and preferences.
**Complexity:** M
**Dependencies:** Story 6.1, Story 2.3, Story 4.5
**Labels:** `frontend`, `settings`

#### SubTask 6.6.1: Create Settings UI
**Description:** Build the settings page with tabs: Providers (health, config), Connectors (status, config, sync), Preferences (theme, notifications).
**Files:**
```
frontend/src/pages/Settings.tsx
frontend/src/components/settings/ProviderSettings.tsx
frontend/src/components/settings/ConnectorSettings.tsx
frontend/src/components/settings/PreferenceSettings.tsx
frontend/tests/Settings.test.tsx
```
**Acceptance Criteria:**
- [ ] Provider health and config displayed
- [ ] Connector settings editable
- [ ] Manual sync triggerable from settings
- [ ] Preferences saved to localStorage

---

## EPIC 7: V2 Connectors

**Description:** Add Apple Notes and Outlook connectors.
**Labels:** `backend`, `connector`, `v2`
**Phase:** 6 — Expansion
**Dependencies:** Epic 4

---

### Story 7.1: Implement Apple Notes Connector
**Complexity:** M
**Dependencies:** Story 4.1
**Spec Reference:** F-009
**Labels:** `backend`, `connector`, `v2`

#### SubTask 7.1.1: Implement AppleScript Extraction and Connector
**Description:** Build the Apple Notes connector using osascript AppleScript bridge. Handle HTML-to-markdown conversion, incremental sync, and macOS platform detection.
**Files:**
```
backend/src/nexuspkm/connectors/apple_notes/connector.py
backend/src/nexuspkm/connectors/apple_notes/extractor.py
backend/tests/unit/test_apple_notes_connector.py
```
**Acceptance Criteria:** Per F-009 acceptance criteria

---

### Story 7.2: Implement Outlook Connector
**Complexity:** L
**Dependencies:** Story 4.2 (MS Graph auth)
**Spec Reference:** F-010
**Labels:** `backend`, `connector`, `v2`, `microsoft`

#### SubTask 7.2.1: Implement Email Ingestion
**Description:** Build email sync with delta queries, thread grouping, and configurable folder filtering.
**Files:**
```
backend/src/nexuspkm/connectors/microsoft/outlook_email.py
backend/tests/unit/test_outlook_email.py
```
**Acceptance Criteria:** Per F-010 email acceptance criteria

#### SubTask 7.2.2: Implement Calendar Ingestion
**Description:** Build calendar event sync with sliding window and cross-referencing to Teams meetings.
**Files:**
```
backend/src/nexuspkm/connectors/microsoft/outlook_calendar.py
backend/tests/unit/test_outlook_calendar.py
```
**Acceptance Criteria:** Per F-010 calendar acceptance criteria

---

## EPIC 8: V3 Connector & Advanced Features

**Description:** Add JIRA connector, schedule management, and proactive context surfacing.
**Labels:** `backend`, `frontend`, `v3`
**Phase:** 7 — Advanced
**Dependencies:** Epic 4, Epic 5, Epic 6

---

### Story 8.1: Implement JIRA Connector
**Complexity:** L
**Dependencies:** Story 4.1
**Spec Reference:** F-011
**Labels:** `backend`, `connector`, `v3`

#### SubTask 8.1.1: Implement JIRA Issue Sync
**Description:** Build JIRA REST API integration with JQL filtering, pagination, comment ingestion, and entity mapping.
**Files:**
```
backend/src/nexuspkm/connectors/jira/connector.py
backend/tests/unit/test_jira_connector.py
```
**Acceptance Criteria:** Per F-011 acceptance criteria

---

### Story 8.2: Implement Schedule & Task Management
**Complexity:** L
**Dependencies:** Story 5.1, Story 7.2 (calendar data)
**Spec Reference:** F-012
**Labels:** `backend`, `frontend`, `intelligence`

#### SubTask 8.2.1: Implement Priority Scoring and Digest
**Description:** Build the priority scoring algorithm, daily digest generation, and team workload calculation.
**Files:**
```
backend/src/nexuspkm/services/schedule.py
backend/src/nexuspkm/api/schedule.py
backend/tests/unit/test_schedule.py
```
**Acceptance Criteria:** Per F-012 acceptance criteria

#### SubTask 8.2.2: Implement Schedule and Workload UI
**Description:** Build the schedule sidebar, team workload dashboard, and priority-sorted task list. Use the frontend-design skill.
**Files:**
```
frontend/src/pages/Schedule.tsx
frontend/src/components/schedule/TeamWorkload.tsx
frontend/src/components/schedule/ActionItemList.tsx
frontend/src/components/schedule/DailyDigest.tsx
```
**Acceptance Criteria:** Per F-012 UI acceptance criteria

---

### Story 8.3: Implement Proactive Context Surfacing
**Complexity:** L
**Dependencies:** Story 5.1, Story 7.2 (calendar)
**Spec Reference:** F-013
**Labels:** `backend`, `frontend`, `intelligence`

#### SubTask 8.3.1: Implement Background Scanners and Notifications
**Description:** Build meeting prep assembly, related content detection, notification system with WebSocket push.
**Files:**
```
backend/src/nexuspkm/services/context_surfacing.py
backend/src/nexuspkm/services/notifications.py
backend/src/nexuspkm/api/notifications.py
backend/tests/unit/test_context_surfacing.py
```
**Acceptance Criteria:** Per F-013 acceptance criteria

#### SubTask 8.3.2: Implement Notification UI
**Description:** Build the notification bell, dropdown panel, and meeting prep cards.
**Files:**
```
frontend/src/components/notifications/NotificationBell.tsx
frontend/src/components/notifications/NotificationPanel.tsx
frontend/src/components/notifications/MeetingPrepCard.tsx
```
**Acceptance Criteria:** Per F-013 UI acceptance criteria

---

## EPIC 9: Automation & Extensibility

**Description:** Build workflow automation integration, evaluate alternative PR review tools, and implement autonomous merge loop.
**Labels:** `infrastructure`, `automation`
**Phase:** 8 — Automation
**Dependencies:** Epic 8

---

### Story 9.1: Implement Extensibility API
**Complexity:** M
**Spec Reference:** F-013 (FR-6)
**Labels:** `backend`, `api`, `automation`

### Story 9.2: Evaluate CodeRabbit / Ellipsis
**Complexity:** S
**Labels:** `infrastructure`, `cicd`

### Story 9.3: Implement Autonomous Merge Loop
**Complexity:** L
**Labels:** `infrastructure`, `cicd`, `automation`

### Story 9.4: Implement Connector Write-Back
**Complexity:** XL
**Labels:** `backend`, `connector`, `automation`

---

## Implementation Order Summary

| Phase | Epic | Stories | Estimated SubTasks | Can Parallelize |
|---|---|---|---|---|
| 0 | Epic 1: Infrastructure | 6 | 9 | Stories 1.1-1.2, 1.3-1.4, 1.5-1.6 |
| 1 | Epic 2: Core Backend | 3 | 7 | Stories 2.1-2.2, then 2.3 |
| 2 | Epic 3: Knowledge Engine | 4 | 6 | Stories 3.1-3.2, then 3.3-3.4 |
| 3 | Epic 4: V1 Connectors | 5 | 9 | Stories 4.3-4.4 (after 4.1-4.2) |
| 4 | Epic 5: Entity Intelligence | 2 | 5 | Sequential |
| 5 | Epic 6: Frontend | 6 | 7 | Stories 6.3-6.5 after 6.1-6.2 |
| 6 | Epic 7: V2 Connectors | 2 | 3 | Stories 7.1-7.2 parallel |
| 7 | Epic 8: V3 + Advanced | 3 | 5 | Stories 8.1 parallel with 8.2-8.3 |
| 8 | Epic 9: Automation | 4 | 4+ | Depends on maturity |
