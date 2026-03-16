# F-006: Entity & Relationship Extraction

**Spec Version:** 1.0
**Date:** 2026-03-16
**ADR Reference:** ADR-001

## Overview

An LLM-powered pipeline that extracts structured entities (people, projects, topics, decisions, action items) and their relationships from ingested documents. Includes entity deduplication, contradiction detection, and confidence scoring. Runs asynchronously as a background process after document ingestion.

## User Stories

- As a user, I want the system to automatically identify people, projects, and topics from my documents
- As a user, I want to see how entities are connected (who works on what, what was decided in which meeting)
- As a user, I want "John Smith" in an email and "John" in a meeting transcript recognized as the same person
- As a user, I want to be notified when new information contradicts existing knowledge

## Functional Requirements

### FR-1: Entity Types

| Entity Type | Properties | Extraction Signals |
|---|---|---|
| Person | name, email, aliases, role, team | Email headers, meeting participants, @mentions, "John said..." |
| Project | name, description, aliases, status | JIRA project keys, repeated topic references, dedicated channels |
| Topic | name, keywords, description | Recurring themes, hashtags, meeting agenda items |
| Decision | summary, context, date | "We decided...", "The decision is...", action verb patterns |
| ActionItem | description, status, due_date, assignee | "TODO:", "Action item:", "John will...", JIRA tickets |
| Meeting | title, date, duration, participants | Calendar events, transcript headers |

### FR-2: Extraction Pipeline

```python
class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity]
    relationships: list[ExtractedRelationship]
    confidence: float

class ExtractedEntity(BaseModel):
    type: EntityType
    name: str
    properties: dict
    confidence: float
    source_span: str          # Text excerpt where entity was found

class ExtractedRelationship(BaseModel):
    source_entity: str        # Entity name
    relationship_type: str    # ATTENDED, MENTIONED_IN, etc.
    target_entity: str
    confidence: float
    context: str              # Text excerpt supporting the relationship
```

Pipeline steps:
1. **LLM Extraction**: send document chunks to LLM with structured extraction prompt
2. **Entity Normalization**: standardize names, resolve aliases
3. **Deduplication**: match against existing entities in graph
4. **Relationship Mapping**: create edges between entities
5. **Confidence Scoring**: assign confidence based on extraction quality
6. **Graph Update**: write new entities/relationships to Kuzu

### FR-3: LLM Extraction Prompt

```
Given the following document, extract all entities and their relationships.

Entity types: Person, Project, Topic, Decision, ActionItem, Meeting

For each entity, provide:
- type: the entity type
- name: the canonical name
- properties: relevant properties (email, role, date, status, etc.)
- confidence: 0.0-1.0 how certain you are

For each relationship, provide:
- source: entity name
- type: relationship type (ATTENDED, MENTIONED_IN, ASSIGNED_TO, RELATED_TO, DECIDED_IN, WORKS_ON, TAGGED_WITH)
- target: entity name
- context: the text that supports this relationship

Return as JSON.

Document:
{document_text}
```

### FR-4: Entity Deduplication

Resolve different references to the same entity:
- **Name matching**: fuzzy match on names (Levenshtein distance < 3)
- **Email matching**: same email = same Person
- **Alias tracking**: when a match is found, add the variant as an alias
- **LLM-assisted**: for ambiguous cases, ask the LLM "Are 'Project Alpha' and 'Alpha Project' the same?"
- **Manual override**: API endpoint to merge/split entities

Resolution priority: email match > exact name match > fuzzy match > LLM-assisted

### FR-5: Contradiction Detection

When new information conflicts with existing knowledge:
- **Date conflicts**: "deadline is March 15" vs existing "deadline is March 20"
- **Status conflicts**: "project is complete" vs existing "project is in progress"
- **Assignment conflicts**: "Alice owns this" vs existing "Bob owns this"

Handling:
1. Flag the contradiction with both old and new values
2. Store as a `Contradiction` record with source references
3. Surface in the UI as a notification
4. Auto-resolve based on recency by default (configurable)

### FR-6: Background Processing

- Entity extraction runs asynchronously after document ingestion completes
- Queue-based: documents enter an extraction queue, processed FIFO
- Configurable concurrency (default: 2 parallel extractions)
- Progress tracking: exposed via API
- Retry on failure with exponential backoff (max 3 retries)

## Non-Functional Requirements

- Extraction must not block document ingestion — runs as a background job
- Entity deduplication must complete in < 1 second per entity
- Graph updates must be atomic — no partial entity/relationship writes
- Extraction queue must survive application restart (persistent queue)

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/entities` | List entities with filtering (type, name search) |
| GET | `/api/entities/{id}` | Get entity details with relationships |
| POST | `/api/entities/merge` | Merge two entities (dedup override) |
| GET | `/api/relationships` | List relationships with filtering |
| GET | `/api/extraction/status` | Extraction queue status |
| GET | `/api/contradictions` | List detected contradictions |
| POST | `/api/contradictions/{id}/resolve` | Resolve a contradiction |

## Testing Strategy

### Unit Tests
- Test LLM extraction prompt parsing (mock LLM returns structured JSON)
- Test entity normalization (name standardization, alias tracking)
- Test deduplication logic (exact match, fuzzy match, email match)
- Test contradiction detection (date, status, assignment conflicts)
- Test confidence scoring algorithm

### Integration Tests
- Test full extraction pipeline: document → LLM → entities → graph
- Test deduplication against existing entities in Kuzu
- Test background queue processing
- Test atomic graph updates (no partial writes on failure)

### Test Fixtures
- Sample documents with known entities and relationships
- Pre-populated Kuzu graph for deduplication testing
- Mock LLM responses with various extraction quality levels

## Dependencies

- F-001 (LLM Provider Abstraction) — for LLM extraction calls
- F-002 (Knowledge Engine Core) — for Kuzu graph access

## Acceptance Criteria

- [ ] Entities are correctly extracted from documents with confidence scores
- [ ] Relationships between entities are identified and stored in the graph
- [ ] Deduplication resolves "John Smith" and "jsmith@company.com" as the same Person
- [ ] Contradictions are detected and surfaced for review
- [ ] Extraction runs asynchronously without blocking ingestion
- [ ] Entity merge API allows manual deduplication correction
- [ ] Extraction survives application restart (persistent queue)
