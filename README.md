# NexusPKM

Personal knowledge management application that consolidates data from Microsoft Teams, Outlook, Obsidian, JIRA, and Apple Notes into a unified local knowledge engine.

## Features

- **Unified Search** — Semantic search across all connected data sources
- **Knowledge Graph** — Automatic entity extraction and relationship mapping
- **AI Chat** — Conversational interface with source attribution
- **Proactive Context** — Meeting prep and related content surfacing
- **Local-First** — All data stored locally, no cloud dependency

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+, FastAPI, Pydantic v2 |
| Frontend | TypeScript, React 18+, Tailwind CSS, shadcn/ui, Vite |
| Knowledge Engine | LlamaIndex, Kuzu (graph), LanceDB (vector) |
| LLM (default) | AWS Bedrock (configurable: OpenAI, Ollama, OpenRouter, LM Studio) |

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) (Python package manager)

### Backend

```bash
cd backend
uv sync
uvicorn nexuspkm.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Configuration

1. Copy example config files:
   ```bash
   cp config/providers.yaml.example config/providers.yaml
   cp config/connectors.yaml.example config/connectors.yaml
   cp config/app.yaml.example config/app.yaml
   ```

2. Set environment variables for API keys (see `config/*.yaml.example` for details).

## Project Structure

```
backend/         Python backend (FastAPI)
frontend/        React frontend (Vite)
config/          YAML configuration files
data/            Local database storage (gitignored)
design/          ADRs, specs, architecture docs
docs/            User-facing documentation
```

## Development

See [design/runbooks/development-workflow.md](design/runbooks/development-workflow.md) for the full development workflow.

```bash
# Backend tests
cd backend && pytest

# Frontend tests
cd frontend && npx vitest run

# Linting
cd backend && ruff check . && ruff format --check .
cd frontend && npx tsc --noEmit
```

## License

MIT
