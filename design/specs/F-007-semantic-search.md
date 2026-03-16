# F-007: Semantic Search

**Spec Version:** 1.0
**Date:** 2026-03-16
**ADR Reference:** ADR-001

## Overview

A comprehensive search system combining full-text matching, vector similarity, and graph-enhanced retrieval. Provides faceted filtering by source type, date range, entity, and topic. Search results include relevance scoring and source attribution.

## User Stories

- As a user, I want to search my knowledge base by meaning, not just keywords
- As a user, I want to filter search results by source type, date range, or topic
- As a user, I want search results to show related entities and connections
- As a user, I want results ranked by relevance with clear attribution

## Functional Requirements

### FR-1: Search API

```python
class SearchRequest(BaseModel):
    query: str
    filters: SearchFilters | None = None
    top_k: int = 20
    include_graph_expansion: bool = True

class SearchFilters(BaseModel):
    source_types: list[SourceType] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    entities: list[str] | None = None       # Filter by entity names
    tags: list[str] | None = None

class SearchResult(BaseModel):
    id: str
    title: str
    excerpt: str                             # Highlighted excerpt
    source_type: SourceType
    source_id: str
    relevance_score: float
    created_at: datetime
    url: str | None
    matched_entities: list[EntitySummary]    # Entities found in this result
    related_documents: list[str]             # IDs of graph-connected documents

class SearchResponse(BaseModel):
    results: list[SearchResult]
    total_count: int
    facets: SearchFacets
    query_entities: list[str]                # Entities detected in the query

class SearchFacets(BaseModel):
    source_types: dict[str, int]             # source_type → count
    date_histogram: list[DateBucket]
    top_entities: list[EntityCount]
    top_tags: list[TagCount]
```

### FR-2: Search Pipeline

1. **Query analysis**: extract entities and key terms from the query
2. **Vector search**: embed query → cosine similarity search in LanceDB
3. **Metadata filtering**: apply date range, source type, tag filters via LanceDB SQL
4. **Graph expansion** (optional): for top vector results, traverse Kuzu graph to find connected documents within 2 hops
5. **Result merging**: combine vector results + graph-expanded results, deduplicate, re-rank
6. **Facet computation**: aggregate result counts by source type, date, entity, tag
7. **Excerpt generation**: extract the most relevant excerpt from each result, highlight matched terms

### FR-3: Relevance Scoring

```
combined_score = (vector_score * 0.6) + (graph_score * 0.3) + (recency_score * 0.1)
```

- **vector_score**: cosine similarity from LanceDB (0-1)
- **graph_score**: number of graph connections to query entities, normalized (0-1)
- **recency_score**: exponential decay based on document age (0-1)
- Weights are configurable

### FR-4: Faceted Filtering

Filters are applied at the LanceDB query level where possible (pre-filter) for performance:
- `source_types`: SQL `WHERE source_type IN (...)`
- `date_from`/`date_to`: SQL `WHERE created_at BETWEEN ... AND ...`
- `tags`: SQL `WHERE array_contains(tags, ...)`
- `entities`: post-filter after graph expansion

### FR-5: Search Suggestions

- As-you-type suggestions from:
  - Recent searches
  - Entity names in the graph
  - Document titles
- Debounced with 300ms delay

## Non-Functional Requirements

- Search response time < 1 second for up to 100K documents
- Facet computation must not significantly increase response time
- Search must work with zero documents (return empty results, not error)
- Graph expansion adds < 200ms to search time

## UI/UX Requirements

### Layout
- Search bar with autocomplete dropdown (top of page)
- Filter sidebar (left): source type checkboxes, date range picker, entity/tag selectors
- Results list (center): title, excerpt with highlights, source badge, timestamp, relevance indicator
- Result cards expandable to show matched entities and related documents

### Interactions
- Clicking a result navigates to the source or opens a detail view
- Filters update results in real-time (debounced)
- "Clear all filters" button
- Result count and active filter summary

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/search` | Execute search query |
| GET | `/api/search/suggest?q={prefix}` | Search suggestions |
| GET | `/api/search/facets` | Available facet values |

## Testing Strategy

### Unit Tests
- Test query analysis (entity extraction from search queries)
- Test relevance scoring formula with known inputs
- Test filter application logic
- Test excerpt generation and highlighting
- Test facet computation

### Integration Tests
- Test full search pipeline with pre-populated LanceDB + Kuzu
- Test that vector search returns semantically relevant results
- Test graph expansion adds relevant connected documents
- Test filtered search narrows results correctly
- Test empty knowledge base returns empty results gracefully

## Dependencies

- F-002 (Knowledge Engine Core) — for LanceDB and Kuzu access
- F-006 (Entity Extraction) — for entity-enhanced search

## Acceptance Criteria

- [ ] Natural language queries return semantically relevant results
- [ ] Source type, date range, entity, and tag filters work correctly
- [ ] Graph expansion surfaces related documents not in direct vector results
- [ ] Results are ranked by combined relevance score
- [ ] Facets accurately reflect result distribution
- [ ] Search suggestions appear within 300ms of typing
- [ ] Search responds in < 1 second for up to 100K documents
- [ ] Empty knowledge base returns empty results without error
