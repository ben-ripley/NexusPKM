# F-002: Knowledge Engine Core

**Spec Version:** 1.0
**Date:** 2026-03-16
**ADR Reference:** ADR-001

## Overview

The core knowledge engine integrates LlamaIndex's PropertyGraphIndex with Kuzu (graph database) and LanceDB (vector database) to provide hybrid storage and retrieval. Documents are ingested through a pipeline that chunks, embeds, stores vectors, extracts entities/relationships, and stores them in the graph.

## User Stories

- As a user, I want ingested documents to be both semantically searchable and connected by relationships
- As a user, I want to re-index my knowledge base without re-fetching from original sources
- As a user, I want to see how many documents are in my knowledge base and their status

## Functional Requirements

### FR-1: Common Document Schema

```python
from pydantic import BaseModel
from datetime import datetime
from enum import Enum

class SourceType(str, Enum):
    TEAMS_TRANSCRIPT = "teams_transcript"
    OBSIDIAN_NOTE = "obsidian_note"
    OUTLOOK_EMAIL = "outlook_email"
    OUTLOOK_CALENDAR = "outlook_calendar"
    JIRA_ISSUE = "jira_issue"
    APPLE_NOTE = "apple_note"

class DocumentMetadata(BaseModel):
    source_type: SourceType
    source_id: str              # Unique ID from the source system
    title: str
    author: str | None = None
    participants: list[str] = []
    tags: list[str] = []
    url: str | None = None      # Deep link back to source
    created_at: datetime
    updated_at: datetime
    synced_at: datetime
    custom: dict = {}           # Source-specific metadata

class Document(BaseModel):
    id: str                     # Internal UUID
    content: str                # Full text content
    metadata: DocumentMetadata
    chunks: list[str] = []      # Populated after chunking
    processing_status: str = "pending"  # pending, processing, indexed, error
```

### FR-2: Ingestion Pipeline

```
Document → Chunking → Embedding → Vector Store (LanceDB)
                                 ↓
                        Entity/Relationship Extraction (LLM)
                                 ↓
                        Graph Store (Kuzu)
```

1. **Chunking**: split document content into overlapping chunks (default: 512 tokens, 50 token overlap). Chunking strategy configurable per source type.
2. **Embedding**: generate vector embeddings for each chunk via the configured embedding provider
3. **Vector storage**: store embeddings + metadata in LanceDB
4. **Entity extraction**: LLM-powered extraction of entities and relationships (see F-006)
5. **Graph storage**: store entities and relationships in Kuzu

### FR-3: LanceDB Vector Store

- Database path: `data/lancedb/`
- Table: `documents` with columns: `id`, `chunk_id`, `text`, `vector`, `source_type`, `source_id`, `title`, `created_at`, `updated_at`
- Embedding dimension: configured per provider (default 1024 for Titan v2)
- Similarity metric: cosine similarity
- Metadata filtering via DuckDB SQL integration

### FR-4: Kuzu Graph Database

- Database path: `data/kuzu/`
- Node tables:
  - `Person(id STRING, name STRING, email STRING, aliases STRING[], first_seen TIMESTAMP, last_seen TIMESTAMP)`
  - `Project(id STRING, name STRING, description STRING, aliases STRING[])`
  - `Topic(id STRING, name STRING, keywords STRING[])`
  - `Decision(id STRING, summary STRING, made_at TIMESTAMP, context STRING)`
  - `ActionItem(id STRING, description STRING, status STRING, due_date TIMESTAMP, assignee_id STRING)`
  - `Meeting(id STRING, title STRING, date TIMESTAMP, duration_minutes INT32, source_id STRING)`
  - `Document(id STRING, title STRING, source_type STRING, source_id STRING, created_at TIMESTAMP)`
- Relationship tables:
  - `ATTENDED(FROM Person, TO Meeting)`
  - `MENTIONED_IN(FROM Person, TO Document, context STRING)`
  - `ASSIGNED_TO(FROM ActionItem, TO Person)`
  - `RELATED_TO(FROM Document, TO Document, relationship STRING, confidence FLOAT)`
  - `DECIDED_IN(FROM Decision, TO Meeting)`
  - `WORKS_ON(FROM Person, TO Project)`
  - `TAGGED_WITH(FROM Document, TO Topic)`
  - `FOLLOWED_UP_BY(FROM ActionItem, TO ActionItem)`
  - `OWNS(FROM Person, TO Project)`
  - `BLOCKS(FROM ActionItem, TO ActionItem)`

### FR-5: Hybrid Retrieval

```python
class RetrievalResult(BaseModel):
    chunks: list[ChunkResult]       # Vector similarity results
    entities: list[EntityResult]     # Graph entity matches
    relationships: list[RelResult]   # Graph relationship paths
    combined_score: float
    sources: list[SourceAttribution]

async def hybrid_retrieve(query: str, top_k: int = 10,
                          filters: dict | None = None) -> RetrievalResult:
    """
    1. Vector search in LanceDB for semantically similar chunks
    2. Extract entities from query
    3. Graph traversal in Kuzu for related entities/documents
    4. Merge and rank results by combined relevance score
    5. Attach source attribution to each result
    """
```

### FR-6: Re-indexing

- Re-index from stored raw documents without re-fetching from sources
- Support full re-index (drop and rebuild) and incremental re-index (changed documents only)
- Re-indexing is triggered via API or on configuration change (e.g., new embedding model)

## Non-Functional Requirements

- Ingestion pipeline must process documents asynchronously (non-blocking)
- Vector search latency < 500ms for 100K chunks
- Graph traversal latency < 200ms for 2-hop queries
- Storage must be durable — survive application restarts
- Ingestion pipeline must be idempotent (re-processing same document produces same result)

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/engine/ingest` | Manually ingest a document |
| POST | `/api/engine/reindex` | Trigger re-indexing |
| GET | `/api/engine/stats` | Document count, entity count, relationship count |
| GET | `/api/engine/status` | Pipeline processing status |

## Testing Strategy

### Unit Tests
- Test chunking logic with various document sizes and types
- Test Document schema validation
- Test hybrid retrieval merging and ranking logic
- Test re-indexing idempotency

### Integration Tests
- Test full ingestion pipeline: Document → chunks → LanceDB + Kuzu
- Test vector search returns semantically relevant results
- Test graph queries return correct entity/relationship paths
- Test hybrid retrieval combines vector + graph results correctly

## Dependencies

- F-001 (LLM Provider Abstraction) — for embedding generation and entity extraction

## Acceptance Criteria

- [ ] Documents ingested through the pipeline are stored in both LanceDB and Kuzu
- [ ] Vector search returns semantically relevant chunks with correct metadata
- [ ] Graph queries return correct entity/relationship results via Cypher
- [ ] Hybrid retrieval combines both result sets with ranked scoring
- [ ] Re-indexing produces identical results from stored raw documents
- [ ] Engine stats endpoint reports accurate counts
- [ ] Pipeline handles concurrent ingestion without data corruption
