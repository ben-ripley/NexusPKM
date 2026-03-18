# NexusPKM

Personal knowledge management application that consolidates data from Teams, Outlook, Obsidian, JIRA, and Apple Notes into a unified local knowledge engine.

## Tech Stack

- **Backend:** Python 3.12+, FastAPI, Pydantic v2, uvicorn
- **Frontend:** TypeScript 5.x, React 18+, Tailwind CSS, shadcn/ui, Vite
- **Knowledge Engine:** LlamaIndex, Kuzu (graph DB), LanceDB (vector DB)
- **LLM Default:** AWS Bedrock (configurable: OpenAI, Ollama, OpenRouter, LM Studio)
- **Testing:** pytest + pytest-asyncio (backend), vitest + Testing Library (frontend)
- **Linting:** ruff (backend), eslint (frontend)
- **Type Checking:** mypy (backend), tsc (frontend)
- **Package Management:** uv (backend), npm (frontend)

## Project Structure

```
backend/src/nexuspkm/     # Python source code
backend/tests/            # pytest tests (unit/, integration/)
frontend/src/             # React source code
frontend/tests/           # vitest tests
config/                   # YAML config files (.example committed, actuals gitignored)
data/                     # Local DB storage (gitignored)
design/                   # ADRs, specs, architecture (read before implementing)
docs/                     # User-facing documentation
```

## Commands

```bash
# Backend
cd backend && uv sync                          # Install dependencies
cd backend && uvicorn nexuspkm.main:app --reload  # Run dev server
cd backend && pytest                           # Run all tests
cd backend && pytest tests/unit                # Run unit tests only
cd backend && ruff check . && ruff format --check .  # Lint
cd backend && mypy src/                        # Type check

# Frontend
cd frontend && npm install                     # Install dependencies
cd frontend && npm run dev                     # Run dev server
cd frontend && npx vitest run                  # Run tests
cd frontend && npx tsc --noEmit                # Type check
cd frontend && npm run build                   # Production build
```

## Per-Task Development Workflow

Follow these steps **in order** for every Jira issue worked on:

1. **Read the Jira issue** — fetch it via MCP and read title, description, acceptance criteria, and dependencies.
2. **Transition to In Progress and assign** — transition the issue to "In Progress" (transition ID `21`) and assign to `557058:1765a43f-ad6f-42f2-a153-efe410493e6c` (Ben Ripley).
3. **Clarify if uncertain** — if and only if requirements are unclear, ask before proceeding. Do not ask about things that are clearly specified.
4. **Plan for non-trivial work** — if the task requires creating or modifying more than a few files, enter plan mode (`EnterPlanMode`) and get approval before writing any code.
5. **Update design docs if needed** — if the work involves functionality not covered in `design/` (adrs/, architecture/, specs/), update the relevant design docs before implementing.
6. **TDD: write tests first** — write failing tests before writing implementation code. Red → Green → Refactor.
7. **Review before committing** — run type checking, linting, and all tests. If the application can be started, verify integration tests pass too.
8. **Commit locally** — use this exact format (no Co-Authored-By):
   ```
   feat(NXP-{id}): {short description}

   {One or two sentences summarizing what the change does and why.}
   ```
9. **Create a pull request** — summarize the changes, reference the Jira issue and spec.
10. **Transition Jira to In Review** — transition the issue to "In Review" (transition ID `31`).

### Development Rules

#### Process
- Read the feature spec in `design/specs/` BEFORE implementing any feature
- Write tests BEFORE implementation (TDD)
- One feature branch per Jira issue: `feature/NXP-{id}-{short-description}`
- Never commit directly to `main`

### Backend Conventions
- All API handlers are async
- Use Pydantic models for all request/response schemas
- Use `structlog` for logging, never `print()`
- Secrets come from environment variables only, never YAML config
- Import order enforced by ruff (isort rules)

### Frontend Conventions
- Use shadcn/ui components — do not install alternative component libraries
- State management via Zustand stores in `src/stores/`
- API calls via TanStack Query hooks in `src/hooks/`
- Use Lucide React for icons

### Patterns to Avoid
- Do not use `any` type in TypeScript — always type explicitly
- Do not use `# type: ignore` in Python — fix the type error
- Do not hardcode API URLs — use environment/config
- Do not store secrets in config files — use env vars
- Do not add dependencies without checking if an existing one covers the need
- Do not write synchronous I/O in the backend — use async

## Key References

- @design/architecture/system-architecture.md — full system architecture
- @design/adrs/ — architectural decisions and rationale
- @design/specs/ — detailed feature specifications
- @design/runbooks/development-workflow.md — complete dev workflow
- @design/implementation-plan.md — phase overview and epic dependency graph
- @design/phases/ — per-phase Jira key index (Jira is source of truth for issue detail)
