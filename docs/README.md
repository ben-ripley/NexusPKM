# NexusPKM User Documentation

NexusPKM is a locally-hosted personal knowledge management application that consolidates information from your daily tools — Teams meetings, email, calendar, Obsidian notes, Jira, and Apple Notes — into a single, searchable knowledge base that you can chat with.

Everything runs on your machine. Your data never leaves.

---

[![CI](https://github.com/ben-ripley/NexusPKM/actions/workflows/ci.yml/badge.svg)](https://github.com/ben-ripley/NexusPKM/actions/workflows/ci.yml)

---

[![GitHub](https://img.shields.io/badge/GitHub-%23121011.svg?logo=github&logoColor=white)](https://github.com/ben-ripley)

[![X](https://img.shields.io/badge/X-%23000000.svg?logo=X&logoColor=white)](https://x.com/benripley)

[![LinkedIn](https://custom-icon-badges.demolab.com/badge/LinkedIn-0A66C2?logo=linkedin-white&logoColor=fff)](https://www.linkedin.com/in/benripley/)

---

## Documentation Index

| Guide | Description |
|---|---|
| [What is NexusPKM?](#what-is-nexuspkm) | Purpose and key concepts |
| [How It Works](how-it-works.md) | The knowledge engine, AI pipeline, and storage |
| [Connectors](connectors.md) | Each data source explained |
| [Configuration](configuration.md) | Config files and environment variables |
| [User Guide](user-guide.md) | Dashboard, chat, search, graph explorer, notifications |
| [Switching LLM Providers](llm-providers.md) | Change between Bedrock, OpenAI, Ollama, etc. |

---

## What is NexusPKM?

Knowledge is scattered. A decision made in a Teams meeting, followed up in an
email, tracked in a JIRA ticket, and referenced in an Obsidian note — none of
those systems know about each other. Finding context means switching between four
apps and reconstructing threads manually.

NexusPKM solves this by pulling all of those sources into one place and building
a unified knowledge graph. You can then:

- **Ask natural language questions** — "What did we decide about the API
  architecture?" — and get answers with citations to the exact source documents
- **Search semantically** — find documents by meaning, not just keyword matches
- **Explore the graph** — see how people, projects, decisions, and action items
  are connected across all your data
- **Get proactive context** — receive pre-meeting briefings assembled
  automatically from past conversations and related documents

### Key design principles

- **Local-first** — the server runs on `127.0.0.1` only; no data leaves your
  machine unless you choose a cloud LLM provider
- **Read-only connectors** — NexusPKM never modifies your source data
- **Incremental sync** — after the initial import, only new or changed content
  is processed; full re-syncs are opt-in
- **Configurable AI** — swap between AWS Bedrock, OpenAI, Ollama (local), or
  other LLM providers without touching any code

---

## Quick start

```bash
# 1. Install backend dependencies
cd backend && uv sync

# 2. Copy and edit configuration files
cp config/providers.yaml.example config/providers.yaml
cp config/connectors.yaml.example config/connectors.yaml
cp config/app.yaml.example config/app.yaml

# 3. Set required environment variables (see Configuration guide)

# 4. Start the backend
cd backend && uvicorn nexuspkm.main:app --host 127.0.0.1 --port 8000

# 5. Start the frontend (separate terminal)
cd frontend && npm install && npm run dev

# 6. Open http://localhost:5173 in your browser
```

On first launch, enable connectors in Settings, trigger an initial sync, and
wait for the knowledge base to build. See the [User Guide](user-guide.md) for
a walkthrough of each feature.
