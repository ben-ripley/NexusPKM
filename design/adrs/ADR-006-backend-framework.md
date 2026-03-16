# ADR-006: Backend Framework

**Status:** Accepted
**Date:** 2026-03-16
**Deciders:** Project Team

## Context

The backend must support:
- REST API endpoints for CRUD operations
- WebSocket connections for streaming chat responses
- Async I/O for concurrent connector sync operations
- Background task scheduling (connector sync, entity extraction)
- Auto-generated API documentation (for future extensibility API)
- Strong typing with Pydantic models

## Alternatives Considered

### Django + Django REST Framework
- **Pros**: Batteries-included, ORM, admin panel, mature
- **Cons**: Synchronous by default (async support is bolted on), heavier than needed, ORM unnecessary since we use Kuzu + LanceDB, slower development for API-first applications

### Flask
- **Pros**: Lightweight, simple, large ecosystem
- **Cons**: No native async support, no built-in WebSocket support, no auto-generated API docs, requires many extensions for our needs

### Litestar
- **Pros**: Modern async framework, good performance, built-in dependency injection
- **Cons**: Smaller community, fewer tutorials, less library support than FastAPI

## Decision

Use **FastAPI** with:

| Concern | Choice |
|---|---|
| Framework | FastAPI |
| Server | Uvicorn (ASGI) |
| Data Validation | Pydantic v2 |
| Background Tasks | FastAPI BackgroundTasks + APScheduler for scheduled jobs |
| WebSocket | FastAPI native WebSocket support |
| Dependency Injection | FastAPI's built-in `Depends()` |
| API Documentation | Auto-generated OpenAPI (Swagger UI + ReDoc) |
| Testing | pytest + httpx (async test client) + pytest-asyncio |

### Why FastAPI

1. **Async-native**: built on Starlette, natively async — critical for concurrent connector syncs and streaming chat
2. **Pydantic integration**: request/response models are Pydantic — seamless with our data models
3. **WebSocket support**: first-class WebSocket handling for streaming LLM responses
4. **Auto-generated OpenAPI**: documentation is always up-to-date, invaluable for the future extensibility API
5. **Type hints**: full Python type hint integration for IDE support and validation
6. **Performance**: one of the fastest Python frameworks
7. **Community**: large, active community with extensive documentation

## Consequences

### Positive
- Async I/O handles concurrent operations efficiently on a single machine
- Pydantic models serve as both API contracts and internal data models
- OpenAPI docs provide a self-documenting API for future automation integrations
- WebSocket support enables real-time streaming chat without additional dependencies
- Strong typing catches bugs early

### Negative
- Async Python has a learning curve and debugging can be harder than sync code
- Background task scheduling requires APScheduler (additional dependency)
- No built-in ORM (not needed, but means manual query construction for Kuzu)

### Risks
- Uvicorn is a single-process server by default — sufficient for personal use but would need Gunicorn with uvicorn workers for multi-user scenarios
