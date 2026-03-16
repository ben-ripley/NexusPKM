# ADR-003: Monorepo Structure

**Status:** Accepted
**Date:** 2026-03-16
**Deciders:** Project Team

## Context

NexusPKM consists of a Python/FastAPI backend and a TypeScript/React frontend. We need a repository structure that supports:
- Git worktrees for parallel development (multiple features developed simultaneously)
- Clear separation between backend and frontend
- Design artifacts (ADRs, specs) versioned alongside code
- User-facing documentation separate from internal design docs
- CI/CD that can build/test components independently

## Decision

Use a **single monorepo** with the following structure:

```
NexusPKM/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                 # Lint, test, build on PR
│   │   └── ai-review.yml         # Claude API PR review
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── ISSUE_TEMPLATE/
├── backend/
│   ├── src/
│   │   └── nexuspkm/
│   │       ├── __init__.py
│   │       ├── main.py            # FastAPI app entry point
│   │       ├── config/            # Configuration management
│   │       ├── providers/         # LLM/embedding provider abstraction
│   │       ├── connectors/        # Data source connectors
│   │       ├── engine/            # Knowledge engine (LlamaIndex/Kuzu/LanceDB)
│   │       ├── api/               # FastAPI route handlers
│   │       ├── models/            # Pydantic data models
│   │       └── services/          # Business logic layer
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── conftest.py
│   ├── pyproject.toml
│   └── README.md
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── services/              # API client
│   │   ├── stores/                # State management
│   │   └── types/
│   ├── tests/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   └── tsconfig.json
├── config/
│   ├── providers.yaml.example
│   └── connectors.yaml.example
├── data/                          # Local data storage (gitignored)
│   ├── kuzu/
│   └── lancedb/
├── design/
│   ├── adrs/
│   ├── specs/
│   ├── architecture/
│   └── runbooks/
├── docs/                          # User-facing documentation
├── .gitignore
├── .claude/
│   └── settings.json
├── CLAUDE.md
├── LICENSE
└── README.md
```

### Git Worktree Compatibility

- All paths are relative to the repo root — no absolute paths in configuration
- The `data/` directory is gitignored, so each worktree gets its own isolated data
- Configuration files use `.example` suffixes; actual configs are gitignored
- No symlinks or hardcoded paths that would break across worktree copies
- CI/CD uses relative paths from the repo root

## Consequences

### Positive
- Single repo simplifies dependency management, code review, and CI/CD
- Design artifacts are versioned alongside the code they describe
- Git worktrees work cleanly — each worktree is a self-contained copy
- Frontend and backend can be built/tested independently via scoped commands
- Clear separation of concerns in directory layout

### Negative
- Larger repo size as both frontend and backend grow
- CI needs to detect which component changed to avoid unnecessary builds
- Git history is shared — frontend and backend changes are interleaved

### Risks
- Monorepo tooling (nx, turborepo) may be needed if build times grow — defer until necessary
