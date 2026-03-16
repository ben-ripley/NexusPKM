# ADR-005: Frontend Technology Stack

**Status:** Accepted
**Date:** 2026-03-16
**Deciders:** Project Team

## Context

NexusPKM requires a locally-hosted web UI that includes:
- Real-time chat interface with streaming LLM responses
- Interactive knowledge graph visualization
- Dashboard with activity feeds and status panels
- Search interface with faceted filtering
- Settings management
- Dark/light mode support
- Beautiful, polished design

## Decision

Use **TypeScript + React + Tailwind CSS + Vite** with the following specific choices:

| Concern | Choice | Rationale |
|---|---|---|
| Language | TypeScript | Type safety, better IDE support, catches errors at compile time |
| Framework | React 18+ | Largest ecosystem, best library support for our needs |
| Styling | Tailwind CSS | Utility-first, fast iteration, consistent design system |
| Component Library | shadcn/ui | High-quality, accessible components built on Radix UI. Copy-paste model means no version lock-in |
| Build Tool | Vite | Fast HMR, native ESM, excellent DX |
| State Management | Zustand | Lightweight, minimal boilerplate, good TypeScript support |
| Data Fetching | TanStack Query | Caching, optimistic updates, request deduplication |
| Graph Visualization | React Force Graph or D3.js | Interactive, zoomable knowledge graph rendering |
| WebSocket | Native WebSocket API | For streaming chat responses from FastAPI |
| Testing | Vitest + Testing Library | Vite-native test runner, component testing |
| Routing | React Router v6 | Standard routing solution |
| Icons | Lucide React | Clean, consistent icon set (used by shadcn/ui) |

### Key UI Pages

1. **Dashboard** — activity feed, connector status, quick search, upcoming items
2. **Chat** — full-width chat interface with source citations
3. **Search** — search bar, results list, filter sidebar
4. **Graph Explorer** — interactive knowledge graph visualization
5. **Settings** — provider config, connector management, preferences

## Consequences

### Positive
- shadcn/ui provides production-grade components with full customization control
- Tailwind + shadcn/ui enables beautiful, consistent design without a heavy CSS framework
- Vite provides fast development iteration
- TypeScript catches frontend bugs early
- All libraries are well-maintained with large communities

### Negative
- shadcn/ui requires manual component installation (copy-paste model)
- Graph visualization libraries have steep learning curves
- WebSocket state management adds complexity over simple REST

### Risks
- Graph visualization performance may degrade with large knowledge graphs — implement virtualization and level-of-detail rendering
