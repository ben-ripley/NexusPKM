# F-001: LLM Provider Abstraction Layer

**Spec Version:** 1.0
**Date:** 2026-03-16
**ADR Reference:** ADR-002

## Overview

A configurable abstraction layer that allows NexusPKM to use any LLM or embedding provider without code changes. Inference and embedding generation are independently configurable. The system supports provider health checks and fallback chains.

## User Stories

- As a user, I want to configure my preferred LLM provider via a YAML file so I can switch between cloud and local models
- As a user, I want to use different providers for inference and embeddings so I can optimize cost and performance
- As a user, I want the system to fall back to a secondary provider if my primary is unavailable
- As a user, I want to see the health status of configured providers in the UI

## Functional Requirements

### FR-1: Provider Interface

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel

class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    usage: dict | None = None

class EmbeddingResponse(BaseModel):
    embedding: list[float]
    model: str
    provider: str

class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str | None = None,
                       temperature: float = 0.7, max_tokens: int = 4096) -> LLMResponse: ...

    @abstractmethod
    async def stream(self, prompt: str, system_prompt: str | None = None,
                     temperature: float = 0.7, max_tokens: int = 4096) -> AsyncIterator[str]: ...

    @abstractmethod
    async def health_check(self) -> ProviderHealth: ...

class BaseEmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[EmbeddingResponse]: ...

    @abstractmethod
    async def embed_single(self, text: str) -> EmbeddingResponse: ...

    @abstractmethod
    async def health_check(self) -> ProviderHealth: ...

    @property
    @abstractmethod
    def dimension(self) -> int: ...
```

### FR-2: Provider Implementations

| Provider | LLM | Embedding | Package |
|---|---|---|---|
| AWS Bedrock | Yes | Yes | `llama-index-llms-bedrock`, `llama-index-embeddings-bedrock` |
| OpenAI | Yes | Yes | `llama-index-llms-openai`, `llama-index-embeddings-openai` |
| Ollama | Yes | Yes | `llama-index-llms-ollama`, `llama-index-embeddings-ollama` |
| OpenRouter | Yes | No | Via OpenAI-compatible endpoint |
| LM Studio | Yes | Yes | Via OpenAI-compatible endpoint (localhost) |

### FR-3: Configuration System

```yaml
# config/providers.yaml
llm:
  primary:
    provider: bedrock
    model: anthropic.claude-sonnet-4-20250514
    region: us-east-1
    max_tokens: 4096
    temperature: 0.7
  fallback:
    provider: ollama
    model: llama3.1:13b
    base_url: http://localhost:11434

embeddings:
  primary:
    provider: bedrock
    model: amazon.titan-embed-text-v2
    region: us-east-1
    dimension: 1024
  fallback:
    provider: ollama
    model: nomic-embed-text
    base_url: http://localhost:11434
    dimension: 768
```

- Environment variables override YAML values: `NEXUSPKM_LLM_PRIMARY_PROVIDER=openai`
- Secrets use env vars only: `AWS_ACCESS_KEY_ID`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`
- Config is validated at startup using Pydantic models

### FR-4: Provider Registry

```python
class ProviderRegistry:
    def get_llm(self) -> BaseLLMProvider:
        """Return the active LLM provider (primary or fallback)."""

    def get_embeddings(self) -> BaseEmbeddingProvider:
        """Return the active embedding provider (primary or fallback)."""

    async def check_health(self) -> dict[str, ProviderHealth]:
        """Check all configured providers and return status."""
```

### FR-5: Fallback Chain

- On provider failure (timeout, auth error, rate limit), automatically try the next provider in the chain
- Log fallback events with warning level
- Expose current active provider via API
- Retry primary provider periodically (configurable interval, default 5 minutes)

## Non-Functional Requirements

- Provider switch must not require application restart (hot-reload config)
- Health check response time < 5 seconds per provider
- Fallback switch must happen within 10 seconds of primary failure
- All provider interactions must be async

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/providers/health` | Health status of all providers |
| GET | `/api/providers/active` | Currently active LLM and embedding providers |
| PUT | `/api/providers/config` | Update provider configuration (hot reload) |

## Testing Strategy

### Unit Tests
- Test each provider implementation with mocked API responses
- Test fallback chain logic (primary fails → fallback activates)
- Test config parsing and validation (valid config, missing fields, invalid provider)
- Test environment variable override logic
- Test health check aggregation

### Integration Tests
- Test actual connectivity to configured providers (skipped in CI, run locally)
- Test hot-reload configuration change

## Dependencies

- None (this is a foundational component)

## Acceptance Criteria

- [ ] All five provider implementations pass unit tests with mocked responses
- [ ] Fallback chain activates within 10 seconds of primary failure
- [ ] Configuration changes via API take effect without restart
- [ ] Health check endpoint returns status for all configured providers
- [ ] Provider switch is transparent to callers (same interface regardless of backend)
- [ ] Environment variables correctly override YAML configuration
