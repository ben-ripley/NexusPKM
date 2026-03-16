# ADR-001: Knowledge Engine Selection

**Status:** Accepted
**Date:** 2026-03-16
**Deciders:** Project Team

## Context

NexusPKM requires a knowledge engine that supports:
- **Hybrid storage**: vector embeddings for semantic search AND a property graph for entity relationships
- **Local-first deployment**: must run on a MacBook Pro M4 Pro (24GB RAM) without external services
- **Zero operational overhead**: no Docker containers, no JVM processes, no separate server management
- **Python ecosystem**: first-class Python SDK for integration with the FastAPI backend
- **Configurable embedding providers**: must work with AWS Bedrock, OpenAI, Ollama, and others
- **Knowledge graph construction**: LLM-powered entity/relationship extraction with Cypher query support

## Alternatives Considered

### Cognee (topoteretes/cognee)
- **Pros**: Purpose-built for knowledge graph + vector hybrid, 14.2K stars, active development, supports Neo4j/Kuzu/NetworkX backends, Apache 2.0
- **Cons**: Still maturing (documentation gaps, limited production guidance), adds an opinionated abstraction layer that may limit customization, Python 3.10-3.13 restriction
- **Verdict**: Strong conceptual alignment but adds a dependency that constrains our architecture. Better used as a reference implementation than a runtime dependency.

### Ruvector (ruvnet/ruvector)
- **Pros**: Innovative self-learning GNN-based search, full Cypher + SPARQL support, MIT license, unified stack
- **Cons**: Small community (3.3K stars), Rust-based with limited Python integration, sparse documentation, no production validation, proprietary RVF container format, limited embedding provider ecosystem
- **Verdict**: Too experimental and complex for a personal PKM foundation. Operational overhead outweighs the self-learning benefits at our scale.

### Neo4j 5.x (standalone)
- **Pros**: Gold standard graph database, native vector index (v5.11+), massive ecosystem, full Cypher + GDS library
- **Cons**: JVM-based (runs under Rosetta 2 on Apple Silicon), requires a running server process, significant memory footprint, Community Edition lacks some features
- **Verdict**: Strong option but the operational overhead of running a JVM process conflicts with our zero-ops requirement.

### Weaviate
- **Pros**: Cross-reference links (graph-adjacent), GraphQL interface, built-in vectorizer modules including AWS Bedrock
- **Cons**: Docker-only for persistent local deployment, opinionated provider configuration baked into schema, heavier operational footprint
- **Verdict**: Docker dependency adds unnecessary friction for a local-first personal application.

### Chroma (standalone)
- **Pros**: Excellent embedded mode, simple Python API, 16K stars, designed for this scale
- **Cons**: Pure vector store with no graph capabilities — would require a separate graph database
- **Verdict**: Good vector store but doesn't address the graph requirement on its own.

### Microsoft GraphRAG
- **Pros**: Purpose-built for knowledge graph construction from documents, hierarchical community detection, backed by Microsoft Research
- **Cons**: Expensive LLM indexing cost, OpenAI-first with limited provider flexibility, designed as an end-to-end pipeline rather than composable library, slow incremental updates
- **Verdict**: Too opinionated and expensive for continuous real-time ingestion. Valuable research reference but not suitable as a core engine.

### LangChain (as orchestration)
- **Pros**: 100K stars, broadest integration ecosystem, supports Neo4j/Kuzu graph stores
- **Cons**: Over-abstraction, frequent breaking API changes, significant complexity for what can be simpler direct implementations
- **Verdict**: LlamaIndex offers better graph-native abstractions (PropertyGraphIndex) with less complexity.

## Decision

Use **LlamaIndex + Kuzu + LanceDB** as the knowledge engine stack:

- **LanceDB** as the embedded vector store: zero-ops, native Apple Silicon, Lance columnar format, DuckDB-powered SQL filtering on metadata, works with any embedding provider via raw vectors or built-in functions
- **Kuzu** as the embedded graph database: zero-ops, native Apple Silicon, full Cypher query language, C++ with Python bindings, ACID transactions, supports LlamaIndex's `KuzuPropertyGraphStore`
- **LlamaIndex** as the orchestration layer: `PropertyGraphIndex` handles entity/relationship extraction via LLM, hybrid retrieval (vector + graph), and provider-agnostic LLM/embedding configuration

This stack runs entirely in-process with **zero external services**. Data persists on disk in `./data/kuzu/` and `./data/lancedb/` directories.

## Consequences

### Positive
- Zero operational overhead — no servers, containers, or processes to manage
- Native Apple Silicon performance for both storage engines
- Full Cypher query support for complex graph traversals
- LlamaIndex's provider abstraction gives us configurable LLM/embedding providers out of the box
- Both Kuzu and LanceDB are actively maintained with growing communities
- Clean separation of concerns: vector search and graph queries can be optimized independently

### Negative
- Kuzu is younger than Neo4j (3.5K vs 13K stars) — smaller community, fewer tutorials
- LanceDB is younger than Chroma/Qdrant — may encounter edge cases
- Two separate storage engines means data consistency must be managed at the application layer
- LlamaIndex API has changed significantly between versions — version pinning is critical
- No built-in replication or multi-machine scaling (acceptable for personal-scale, but limits future growth)

### Risks
- If Kuzu or LanceDB development stalls, migration to alternatives (Neo4j, Chroma) is feasible but non-trivial
- LlamaIndex's `PropertyGraphIndex` is relatively new — may have undiscovered limitations
- Mitigation: abstract storage behind our own interfaces so backends can be swapped
