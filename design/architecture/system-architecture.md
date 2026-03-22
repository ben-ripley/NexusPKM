# NexusPKM System Architecture

**Version:** 1.1
**Date:** 2026-03-22

## 1. Overview

NexusPKM is a locally-hosted personal knowledge management application that consolidates information from multiple sources (Teams, Outlook, Obsidian, JIRA, Apple Notes) into a unified knowledge engine, enabling semantic search, knowledge graph exploration, and AI-powered chat.

## 2. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│              Electron Shell (Main Process — Node.js)             │
│   Window Management │ System Tray │ Backend Lifecycle │ IPC      │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │              Presentation Layer (Renderer)                 │  │
│  │          TypeScript / React / Tailwind / shadcn/ui         │  │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌─────────┐  │  │
│  │  │Dashbrd │ │  Chat  │ │ Search │ │ Graph  │ │Settings │  │  │
│  │  └────────┘ └────────┘ └────────┘ └────────┘ └─────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │           Child Process (FastAPI / uvicorn)                │  │
│  │           Spawned and managed by main process              │  │
│  └────────────────────────────────────────────────────────────┘  │
└───────────────────────┬──────────────────────────────────────────┘
                        │ HTTP REST + WebSocket (127.0.0.1)

Note: When running as a web app (npm run dev), the Electron shell is
absent and the browser connects to the FastAPI server directly.
```

```
┌──────────────────────────────────────────────────────────────────┐
│                  Presentation Layer (Frontend)                    │
│             TypeScript / React / Tailwind / shadcn/ui            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐│
│  │Dashboard │ │  Chat    │ │  Search  │ │  Graph   │ │Settings││
│  │          │ │Interface │ │          │ │ Explorer │ │        ││
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘│
└───────────────────────┬──────────────────────────────────────────┘
                        │ HTTP REST + WebSocket
┌───────────────────────▼──────────────────────────────────────────┐
│                    API Layer (FastAPI)                            │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌──────────────────┐│
│  │  REST     │ │ WebSocket │ │ Background│ │   Notification   ││
│  │ Endpoints │ │  Chat     │ │  Tasks    │ │    Service       ││
│  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └────────┬─────────┘│
└────────┼──────────────┼─────────────┼────────────────┼───────────┘
         │              │             │                │
┌────────▼──────────────▼─────────────▼────────────────▼───────────┐
│                  Service Layer (Business Logic)                    │
│  ┌──────────────┐ ┌───────────────┐ ┌────────────────────────┐  │
│  │  Ingestion   │ │   Retrieval   │ │  Entity Extraction     │  │
│  │  Service     │ │   Service     │ │  Service               │  │
│  └──────┬───────┘ └───────┬───────┘ └──────────┬─────────────┘  │
│         │                 │                     │                │
│  ┌──────▼─────────────────▼─────────────────────▼─────────────┐ │
│  │              LlamaIndex Orchestration Layer                 │ │
│  │         PropertyGraphIndex + Hybrid Retrieval               │ │
│  └──────┬──────────────────────────────────┬──────────────────┘ │
│         │                                  │                    │
│  ┌──────▼──────────┐              ┌────────▼─────────┐         │
│  │    LanceDB      │              │      Kuzu        │         │
│  │  (Vector Store)  │              │  (Graph Store)   │         │
│  │  data/lancedb/  │              │  data/kuzu/      │         │
│  └─────────────────┘              └──────────────────┘         │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │            LLM Provider Abstraction Layer                   ││
│  │   AWS Bedrock │ OpenAI │ OpenRouter │ Ollama │ LM Studio   ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
         │
┌────────▼────────────────────────────────────────────────────────┐
│                     Connector Layer                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────┐ ┌──────────┐│
│  │  Teams   │ │ Obsidian │ │ Outlook  │ │ JIRA  │ │  Apple   ││
│  │(Graph API)│ │(FS Watch)│ │(Graph API)│ │(REST) │ │  Notes   ││
│  └──────────┘ └──────────┘ └──────────┘ └───────┘ └──────────┘│
└─────────────────────────────────────────────────────────────────┘
```

## 3. Data Flow Diagrams

### 3.1 Ingestion Flow

```
Source (Teams/Obsidian/etc.)
  │
  ▼
Connector.fetch()
  │ Produces: Document (common schema)
  ▼
Ingestion Service
  │
  ├─► Chunking (512 tokens, 50 overlap)
  │     │
  │     ▼
  │   Embedding (via LLM Provider)
  │     │
  │     ▼
  │   LanceDB.store(chunks + vectors + metadata)
  │
  └─► Entity Extraction Queue (async)
        │
        ▼
      LLM Extract (entities + relationships)
        │
        ├─► Deduplication (match against existing)
        │
        ▼
      Kuzu.store(entities + relationships)
```

### 3.2 Query Flow (Chat/Search)

```
User Query
  │
  ▼
Query Analysis (extract entities, intent)
  │
  ├─► Vector Search (LanceDB)
  │     │ Returns: top-k similar chunks
  │     ▼
  │   Chunk Results (with metadata)
  │
  ├─► Graph Traversal (Kuzu)
  │     │ Cypher: MATCH paths from query entities
  │     ▼
  │   Entity/Relationship Results
  │
  ▼
Result Merger + Ranker
  │ Combined score = vector(0.6) + graph(0.3) + recency(0.1)
  ▼
Context Assembly
  │ Top results formatted as LLM context
  ▼
LLM Generation (streaming)
  │ System prompt + context + user query
  ▼
Response + Source Attribution
```

### 3.3 Entity Extraction Flow

```
Ingested Document
  │
  ▼
Extraction Queue (FIFO, persistent)
  │
  ▼
LLM Structured Extraction
  │ Prompt: extract entities + relationships as JSON
  ▼
Entity Normalization
  │ Standardize names, parse properties
  ▼
Deduplication Check
  │ Match against existing entities in Kuzu
  │ Methods: email match > exact name > fuzzy > LLM-assisted
  ▼
Contradiction Check
  │ Compare new facts against existing
  │ Flag conflicts for resolution
  ▼
Atomic Graph Update
  │ MERGE entities, CREATE relationships
  ▼
Notification (if new connections/contradictions found)
```

## 4. Component Interactions

### 4.1 Startup Sequence

**Electron desktop mode:**
0. Electron main process starts; spawns `uvicorn nexuspkm.main:app` as a child process, then polls `GET /health` until healthy (timeout 10s). Shows splash screen while waiting.

**FastAPI server startup (steps 1–7, regardless of how uvicorn was launched):**
1. Load configuration (`config/providers.yaml`, `config/connectors.yaml`)
2. Initialize LLM provider registry, run health checks
3. Initialize LanceDB and Kuzu databases
4. Initialize LlamaIndex PropertyGraphIndex
5. Start connector sync scheduler (APScheduler)
6. Start FastAPI server (uvicorn)
7. Serve frontend static files (web mode) — in Electron mode, renderer loads built files via `file://`

**Electron post-backend-ready:**
8. Main process receives healthy response from `/health`; hides splash, loads renderer URL

### 4.2 Key Component Dependencies

```
Frontend ──► FastAPI REST/WS
               │
               ├──► Retrieval Service ──► LlamaIndex ──► LanceDB + Kuzu
               │                                    └──► LLM Provider
               ├──► Ingestion Service ──► LlamaIndex ──► LanceDB + Kuzu
               │         │
               │         └──► Connector Registry ──► Individual Connectors
               │
               ├──► Entity Service ──► Kuzu
               │
               └──► Notification Service ──► SQLite
```

## 5. Security Considerations

### 5.1 Authentication & Token Storage
- Microsoft Graph OAuth2 tokens: encrypted at rest in `data/.tokens/`
- JIRA API tokens: environment variables only, never in config files
- LLM API keys: environment variables only
- `.tokens/` directory is gitignored

### 5.2 Local-First Security Model
- Application runs on localhost only (no external network access to the server)
- No built-in user authentication for v1 (single user, local access)
- Future: add session-based auth if network access is needed

### 5.3 Data Protection
- All data stored locally in `data/` directory
- Sensitive data (tokens, keys) use environment variables
- Future: encryption at rest for the `data/` directory
- No telemetry or data exfiltration

### 5.4 API Security
- FastAPI serves on `127.0.0.1` only (not `0.0.0.0`)
- CORS configured for localhost only
- No API key required for v1 (localhost access implies physical access)

## 6. Configuration Management

### 6.1 Configuration Hierarchy
1. Default values (hardcoded)
2. YAML config files (`config/*.yaml`)
3. Environment variables (override YAML)
4. API runtime config (override env vars, non-persistent)

### 6.2 Configuration Files
```
config/
├── providers.yaml       # LLM/embedding provider settings
├── connectors.yaml      # Connector settings and credentials
└── app.yaml             # General application settings
```

### 6.3 Environment Variables
```
# LLM Providers
AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
OPENAI_API_KEY
OPENROUTER_API_KEY

# Connectors
MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET
JIRA_EMAIL, JIRA_API_TOKEN

# Application
NEXUSPKM_DATA_DIR (default: ./data)
NEXUSPKM_LOG_LEVEL (default: INFO)
```

## 7. Monitoring & Logging

### 7.1 Logging
- Structured JSON logging via `structlog`
- Log levels: DEBUG, INFO, WARNING, ERROR
- Log destinations: stdout (for development), file rotation (for production)
- Per-component log namespaces: `nexuspkm.engine`, `nexuspkm.connectors.teams`, etc.

### 7.2 Health Endpoints
| Endpoint | Description |
|---|---|
| `GET /health` | Application health (DB connectivity, provider status) |
| `GET /api/providers/health` | LLM/embedding provider health |
| `GET /api/connectors/status` | All connector sync statuses |

### 7.3 Metrics (Future)
- Documents ingested (total, per source, per day)
- Entities/relationships in graph
- Query latency (p50, p95, p99)
- LLM token usage per provider

## 8. Deployment Model

### 8.1 Deployment Options

**Production (Electron .dmg installer — primary):**
```bash
cd frontend && npm run electron:dist
# Produces release/NexusPKM-{version}.dmg
# Double-click to install; app manages backend lifecycle automatically
```

**Development (Electron with HMR):**
```bash
cd frontend && npm run electron:dev
# electron-vite starts Vite dev server + Electron main process
# Backend spawned automatically; renderer HMR enabled
```

**Development (web browser — unchanged fallback):**
```bash
# Terminal 1
cd backend && uvicorn nexuspkm.main:app --host 127.0.0.1 --port 8000

# Terminal 2
cd frontend && npm run dev
# Open http://localhost:5173 in browser
```

### 8.2 Future: Docker Compose
```yaml
services:
  app:
    build: .
    ports:
      - "127.0.0.1:8000:8000"
    volumes:
      - ./data:/app/data
      - ./config:/app/config
    env_file: .env
```

## 9. Technology Stack Summary

| Layer | Technology | Purpose |
|---|---|---|
| Desktop Shell | Electron, electron-vite, electron-builder | Native wrapper, backend lifecycle, tray |
| Frontend | React, TypeScript, Tailwind, shadcn/ui, Vite | UI |
| API | FastAPI, Uvicorn, Pydantic | REST + WebSocket |
| Orchestration | LlamaIndex | RAG pipeline, PropertyGraphIndex |
| Vector Store | LanceDB | Semantic search, embeddings |
| Graph Store | Kuzu | Entity relationships, Cypher queries |
| LLM (default) | AWS Bedrock (Claude) | Inference, extraction |
| Embedding (default) | AWS Bedrock (Titan) | Vector embeddings |
| Background Jobs | APScheduler | Connector sync, extraction queue |
| Notifications | SQLite | Notification storage |
| Logging | structlog | Structured logging |
| Testing | pytest, vitest, Playwright | Backend, frontend, E2E |

## 10. Scalability Considerations (Future)

Current architecture is designed for single-user, single-machine deployment. Future scaling paths:

- **Multi-user**: add authentication, per-user data isolation in Kuzu/LanceDB
- **Remote deployment**: Docker Compose on a cloud VM, add HTTPS termination
- **Performance**: if vector search slows beyond 1M chunks, migrate LanceDB to Qdrant server mode
- **Graph scale**: if Kuzu exceeds 10M nodes, evaluate Neo4j migration
- **Distributed sync**: if connector sync becomes bottlenecked, introduce a task queue (Celery/Redis)
