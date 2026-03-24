---
title: Configuration
nav_order: 4
has_children: true
---

# Configuration Reference

Nexus PKM is configured through a combination of YAML files and environment variables. YAML files control application behavior; environment variables supply secrets and can override YAML values.

---

## Configuration files

The `config/` directory contains three YAML files. Example files are checked into the repository; copy them and fill in your values before first run.

```bash
cp config/app.yaml.example config/app.yaml
cp config/providers.yaml.example config/providers.yaml
cp config/connectors.yaml.example config/connectors.yaml
```

The actual `*.yaml` files are gitignored and will never be committed.

---

## app.yaml

Controls the server, storage, logging, chunking, and retrieval behaviour.

```yaml
server:
  host: 127.0.0.1   # Never change this to 0.0.0.0 — keeps the server local-only
  port: 8000

data:
  dir: ./data       # Root directory for LanceDB, Kuzu, and token storage

logging:
  level: INFO       # DEBUG | INFO | WARNING | ERROR
  format: json

chunking:
  size: 512         # Tokens per chunk (1 token ≈ ¾ of a word; 512 tokens ≈ 350–400 words)
  overlap: 50       # Tokens shared between consecutive chunks

retrieval:
  vector_weight: 0.6   # Weight of semantic similarity in combined score
  graph_weight: 0.3    # Weight of graph connection strength
  recency_weight: 0.1  # Weight of document recency
  top_k: 10            # Chunks retrieved per query to use as LLM context
```

**`chunking.size`** controls how documents are split before embedding. Each chunk is embedded and stored as an individual unit in LanceDB. Smaller chunks produce more targeted search hits; larger chunks provide more surrounding context per result but dilute the embedding signal.

**`chunking.overlap`** prevents sentences at chunk boundaries from losing context. Each chunk shares this many tokens with the next — the window slides forward by `size − overlap` tokens each step. 50 tokens (≈ 2–3 sentences) is enough to avoid hard cuts in the middle of a thought.

> Changing chunking settings requires deleting `data/lancedb/` and re-ingesting, because existing chunks in the vector store were built with the old settings.

**`retrieval.top_k`** is the number of chunks retrieved from LanceDB and fed to the LLM as context for each chat query or search. Increase it if answers feel incomplete (more context); decrease it if responses are slow or unfocused (less noise in the context window).

**Retrieval weights** must sum to 1.0. Increasing `graph_weight` makes the system prioritize documents that are well-connected in the knowledge graph. Increasing `vector_weight` puts more emphasis on semantic similarity.

**Environment variable overrides:**

| Variable | Overrides |
|---|---|
| `NEXUSPKM_DATA_DIR` | `data.dir` |
| `NEXUSPKM_LOG_LEVEL` | `logging.level` |

---

## providers.yaml

Controls which LLM and embedding model the application uses. See the dedicated [LLM Providers](llm-providers.md) guide for full details on each provider option.

```yaml
llm:
  primary:
    provider: bedrock    # bedrock | openai | ollama | openrouter | lm_studio
    model: us.anthropic.claude-sonnet-4-20250514-v1:0
    region: us-east-1
  fallback:             # Optional — used if primary fails
    provider: ollama
    model: qwen2.5:14b
    base_url: http://localhost:11434

embedding:
  primary:
    provider: bedrock
    model: amazon.titan-embed-text-v2:0
    region: us-east-1
    dimensions: 1024
  fallback:
    provider: ollama
    model: mxbai-embed-large
    base_url: http://localhost:11434
    dimensions: 1024
```

**Key rule:** `llm` and `embedding` can use different providers. For example, you might use OpenRouter for chat (wide model selection) and Ollama for embeddings (free, fast, local).

**Changing the embedding model** requires deleting `data/lancedb/` before restarting, because the stored vectors will have the wrong dimensions.

---

## connectors.yaml

Enables and configures each data source connector. Credentials are never stored here — use environment variables.

```yaml
teams:
  enabled: false
  sync_interval_minutes: 60
  # Credentials: MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET

outlook:
  enabled: false
  sync_interval_minutes: 15
  folders:
    - Inbox
    - Sent Items
  # Limit initial email import to avoid ingesting your entire mailbox:
  # email_lookback_date: "2024-01-01"
  # calendar_lookback_date: "2024-01-01"
  # Credentials: shared with Teams (MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET)

obsidian:
  enabled: false
  vault_path: ~/Documents/Obsidian
  sync_interval_minutes: 5
  exclude_patterns:
    - ".obsidian/"
    - ".trash/"
    - "templates/"

jira:
  enabled: false
  base_url: https://your-instance.atlassian.net
  sync_interval_minutes: 30
  jql_filter: "assignee = currentUser() ORDER BY updated DESC"
  # Credentials: JIRA_EMAIL, JIRA_API_TOKEN

apple_notes:
  enabled: false
  sync_interval_minutes: 15
  # No credentials needed — uses macOS AppleScript
```

---

## Environment variables

Secrets must be provided as environment variables. The application will not start if required variables for enabled connectors are missing.

### LLM Providers

| Variable | Used by |
|---|---|
| `AWS_ACCESS_KEY_ID` | Bedrock |
| `AWS_SECRET_ACCESS_KEY` | Bedrock |
| `AWS_DEFAULT_REGION` | Bedrock |
| `OPENAI_API_KEY` | OpenAI |
| `OPENROUTER_API_KEY` | OpenRouter |

Ollama and LM Studio are local servers — no API keys needed.

### Connectors

| Variable | Used by |
|---|---|
| `MS_TENANT_ID` | Teams, Outlook |
| `MS_CLIENT_ID` | Teams, Outlook |
| `MS_CLIENT_SECRET` | Teams, Outlook |
| `JIRA_EMAIL` | JIRA |
| `JIRA_API_TOKEN` | JIRA |

Apple Notes and Obsidian require no environment variables.

### Application

| Variable | Effect |
|---|---|
| `NEXUSPKM_DATA_DIR` | Override the data directory (default: `./data`) |
| `NEXUSPKM_LOG_LEVEL` | Override log level (default: `INFO`) |

### Setting environment variables

**For development** — add to your shell profile or a `.env` file (gitignored):
```bash
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=us-east-1
```

**For production (Electron app)** — configure in the Electron environment or use a `.env` file in the project root (gitignored).

---

## Configuration precedence

When the same setting can be specified in multiple places, this order applies (later wins):

1. Hardcoded defaults
2. YAML config file value
3. Environment variable
4. Runtime API update (non-persistent, resets on restart)

---

## Runtime configuration updates

Some settings can be changed at runtime without restarting the backend:

```bash
# Reload providers config from disk (after editing providers.yaml)
curl -X PUT http://127.0.0.1:8000/api/providers/config

# Update connector settings
curl -X PUT http://127.0.0.1:8000/api/connectors/jira/config \
  -H "Content-Type: application/json" \
  -d '{"sync_interval_minutes": 60}'
```

Changes to chunking or embedding settings require a restart and potentially a re-index (see [How It Works](how-it-works.md)).

---

## Verifying your configuration

```bash
# Application health (checks DB connectivity and provider status)
curl http://127.0.0.1:8000/health

# LLM and embedding provider health
curl http://127.0.0.1:8000/api/providers/health | python3 -m json.tool

# Which provider is currently active
curl http://127.0.0.1:8000/api/providers/active | python3 -m json.tool

# All connector statuses
curl http://127.0.0.1:8000/api/connectors/status | python3 -m json.tool
```
