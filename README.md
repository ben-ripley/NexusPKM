# Nexus PKM

Personal knowledge management application that consolidates data from Microsoft Teams, Outlook, Obsidian, JIRA, and Apple Notes into a unified local knowledge engine.

Personal knowledge management application that consolidates data from Microsoft Teams, Outlook, Obsidian, JIRA, and Apple Notes into a unified local knowledge engine.

#### Project Status
[![CI](https://github.com/ben-ripley/NexusPKM/actions/workflows/ci.yml/badge.svg)](https://github.com/ben-ripley/NexusPKM/actions/workflows/ci.yml) 


#### Technology Stack
[![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=fff)](#) [![FastAPI](https://img.shields.io/badge/FastAPI-009485.svg?logo=fastapi&logoColor=white)](#) [![Pydantic](https://img.shields.io/badge/Pydantic-E92063?logo=Pydantic&logoColor=white)](#) [![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=fff)](#) [![React](https://img.shields.io/badge/React-%2320232a.svg?logo=react&logoColor=%2361DAFB)](#) [![SQLite](https://img.shields.io/badge/SQLite-%2307405e.svg?logo=sqlite&logoColor=white)](#) [![Electron](https://img.shields.io/badge/Electron-2B2E3A?logo=electron&logoColor=fff)](#) 

[![AWS](https://custom-icon-badges.demolab.com/badge/AWS-%23FF9900.svg?logo=aws&logoColor=white)](#) [![OpenAPI](https://img.shields.io/badge/OpenAPI-6BA539?logo=openapiinitiative&logoColor=white)](#) [![OpenRouter](https://img.shields.io/badge/OpenRouter-94A3B8?logo=openrouter&logoColor=fff)](#) [![Ollama](https://img.shields.io/badge/Ollama-fff?logo=ollama&logoColor=000)](#) [![Qwen](https://custom-icon-badges.demolab.com/badge/Qwen-605CEC?logo=qwen&logoColor=fff)](#) 

#### Connect with me!
[![GitHub](https://img.shields.io/badge/GitHub-%23121011.svg?logo=github&logoColor=white)](https://github.com/ben-ripley) [![LinkedIn](https://custom-icon-badges.demolab.com/badge/LinkedIn-0A66C2?logo=linkedin-white&logoColor=fff)](https://www.linkedin.com/in/benripley/) [![Instagram](https://img.shields.io/badge/Instagram-%23E4405F.svg?logo=Instagram&logoColor=white)](https://www.instagram.com/ben.ripley.photo/) [![X](https://img.shields.io/badge/X-%23000000.svg?logo=X&logoColor=white)](https://x.com/benripley) 


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
uv sync --extra dev
uv run uvicorn nexuspkm.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Electron App

Run as a desktop app (development, with HMR):

```bash
cd frontend && npm run electron:dev
```

The backend is spawned automatically. No need to start it separately.

For a production build:

```bash
cd frontend && npm run electron:dist
# Produces release/NexusPKM-{version}.dmg
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
