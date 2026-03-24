---
title: LLM Providers
nav_order: 6
---

# LLM Providers

Nexus PKM's provider abstraction layer lets you change the LLM or embedding backend with a config file edit and an environment variable — no code changes required.

---

## Why this matters

Nexus PKM uses LLMs for three things:

1. **Inference** — answering questions, summarising, generating chat responses
2. **Entity extraction** — pulling people, projects, topics, and relationships out of ingested documents
3. **Embeddings** — converting text into vectors for semantic search

All three go through the same abstraction, so swapping the provider changes the behaviour of the entire pipeline at once.

Reasons you might want to swap:

- **Cost** — cloud providers charge per token; local models are free after hardware investment
- **Privacy** — local models keep all data on-device; nothing leaves the machine
- **Latency** — a well-sized local model on Apple Silicon can be faster than a round-trip to a cloud API for short prompts
- **Availability** — local models work offline; cloud APIs go down
- **Quality** — frontier cloud models (Claude, GPT-4o) produce better extraction and reasoning than most local models of equivalent size
- **Experimentation** — different models have different strengths; you can A/B test by swapping and re-ingesting a small corpus

---

## Cloud vs local trade-offs

| | Cloud (Bedrock, OpenAI, OpenRouter) | Local (Ollama, LM Studio) |
|---|---|---|
| **Privacy** | Data sent to third-party servers | Fully on-device |
| **Cost** | Pay per token | Free (electricity + hardware) |
| **Quality** | Best-in-class (Claude, GPT-4o) | Good; smaller gap with recent models |
| **Speed** | Network-dependent; ~1–3 s TTFT | Depends on hardware; instant on M-series |
| **Offline** | No | Yes |
| **Setup** | API key + env var | Install Ollama / LM Studio, pull model |
| **Model choice** | Managed by provider | Full control; any GGUF / Ollama model |
| **Rate limits** | Yes (varies by tier) | None |

For a personal PKM where data sensitivity matters, the local trade-off is compelling once you have the hardware to run a capable model.

---

## Why qwen2.5:14b and mxbai-embed-large?

I'm using a Mac M4 Pro with 24GB unified memory and have found these are the ideal models for my hardware. Your mileage may vary, so experiment.

### qwen2.5:14b — inference

The M4 Pro with 24 GB unified memory can hold a 14B-parameter model entirely in memory at Q4 quantisation (~9 GB), leaving headroom for the OS, Electron, and the Python backend. This means:

- **No layer offloading** — the entire model runs on the Neural Engine / GPU metal, not split between RAM and disk
- **Sustained throughput** — ~40–60 tokens/s on M4 Pro, fast enough for interactive chat and background extraction
- **Quality ceiling** — Qwen 2.5 14B scores competitively with much larger models on reasoning and instruction-following benchmarks, and has strong multilingual capability if your notes contain non-English content
- **Context length** — 128K context window, sufficient for long email threads and Obsidian notes

A 7B model would be faster, but noticeably weaker on entity extraction. A 32B model would be higher quality, but would require swapping between RAM and disk, causing severe latency spikes.

### mxbai-embed-large — embeddings

mxbai-embed-large (335M parameters, 1024 dimensions) is the best-performing embedding model available in Ollama for its size class:

- **MTEB benchmark** — ranks above OpenAI `text-embedding-3-small` on several retrieval tasks despite being a fraction of the cost
- **1024 dimensions** — matches the LanceDB schema default, so no migration is needed when switching from Bedrock Titan
- **Speed** — ~10–20 ms per chunk on M4 Pro; ingestion is not the bottleneck
- **Size** — 335M parameters fit comfortably alongside the inference model within 24 GB

---

## Supported providers

| Provider | LLM | Embedding | Notes |
|---|---|---|---|
| `bedrock` | Yes | Yes | AWS-hosted Claude, Titan; requires AWS credentials |
| `openai` | Yes | Yes | GPT-4o, text-embedding-3; requires `OPENAI_API_KEY` |
| `openrouter` | Yes | No | Routes to many cloud models; requires `OPENROUTER_API_KEY` |
| `ollama` | Yes | Yes | Local; requires Ollama running on `localhost:11434` |
| `lm_studio` | Yes | Yes | Local; OpenAI-compatible endpoint from LM Studio |

---

## Configuration

Edit `config/providers.yaml` (copy from `providers.yaml.example` if it does not exist). Restart the backend after changes, or use `PUT /api/providers/config` for a hot reload without restart.

### AWS Bedrock (default)

```yaml
llm:
  primary:
    provider: bedrock
    model: us.anthropic.claude-sonnet-4-20250514-v1:0
    region: us-east-1

embedding:
  primary:
    provider: bedrock
    model: amazon.titan-embed-text-v2:0
    region: us-east-1
    dimensions: 1024
```

Environment variables required:
```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=us-east-1
```
or if you authenticate via SSO:
```bash
export AWS_PROFILE=...
export AWS_DEFAULT_REGION=us-east-1
```

---

### Ollama (local — recommended for Mac M4 Pro 24 GB)

Pull the models first:
```bash
ollama pull qwen2.5:14b
ollama pull mxbai-embed-large
```

```yaml
llm:
  primary:
    provider: ollama
    model: qwen2.5:14b
    base_url: http://localhost:11434

embedding:
  primary:
    provider: ollama
    model: mxbai-embed-large
    base_url: http://localhost:11434
    dimensions: 1024
```

No environment variables required. Ollama must be running (`ollama serve`).

---

### OpenAI

```yaml
llm:
  primary:
    provider: openai
    model: gpt-4o

embedding:
  primary:
    provider: openai
    model: text-embedding-3-large
    dimensions: 1024
```

Environment variable required:
```bash
export OPENAI_API_KEY=sk-...
```

---

### OpenRouter

OpenRouter provides access to many cloud models (Claude, GPT-4o, Llama, Gemini) through a single API key. Embedding is not supported — pair with Ollama or Bedrock for embeddings.

```yaml
llm:
  primary:
    provider: openrouter
    model: anthropic/claude-sonnet-4-5

embedding:
  primary:
    provider: ollama
    model: mxbai-embed-large
    base_url: http://localhost:11434
    dimensions: 1024
```

Environment variable required:
```bash
export OPENROUTER_API_KEY=sk-or-...
```

---

### LM Studio (local)

Start LM Studio, load a model, and enable the local server (default port 1234).

```yaml
llm:
  primary:
    provider: lm_studio
    model: qwen2.5-14b-instruct  # must match the model name shown in LM Studio
    base_url: http://localhost:1234/v1

embedding:
  primary:
    provider: lm_studio
    model: text-embedding-nomic-embed-text-v1.5
    base_url: http://localhost:1234/v1
    dimensions: 768
```

No environment variables required.

---

## Adding a fallback provider

Any provider can have an optional fallback. If the primary fails (network error, auth failure, rate limit), the system automatically switches to the fallback and retries the primary every 5 minutes.

```yaml
llm:
  primary:
    provider: bedrock
    model: us.anthropic.claude-sonnet-4-20250514-v1:0
    region: us-east-1
  fallback:
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

---

## Verifying the active provider

```bash
# Check health of all configured providers
curl http://127.0.0.1:8000/api/providers/health | python3 -m json.tool

# Check which provider is currently active
curl http://127.0.0.1:8000/api/providers/active | python3 -m json.tool
```

---

## Important: switching embedding providers

The embedding model determines the vector dimensions stored in LanceDB. If you switch embedding providers and the new model uses different dimensions, the existing vector index will be incompatible and semantic search will break.

To switch embedding providers safely:

1. Stop the backend
2. Delete `data/lancedb/` (this wipes the vector index)
3. Update `providers.yaml` with the new embedding config
4. Restart — the next sync will re-embed all documents from scratch

This does **not** affect the graph database (`data/kuzu/`) — entities and relationships are preserved.
