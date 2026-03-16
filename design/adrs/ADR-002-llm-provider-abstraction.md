# ADR-002: LLM Provider Abstraction Layer

**Status:** Accepted
**Date:** 2026-03-16
**Deciders:** Project Team

## Context

NexusPKM processes sensitive corporate data alongside personal notes. The ability to route LLM inference and embedding generation through different providers — from cloud APIs (AWS Bedrock, OpenAI) to local models (Ollama, LM Studio) — is a core requirement. The user must be able to:

- Switch providers without code changes
- Use different providers for different concerns (e.g., Bedrock for embeddings, Ollama for inference)
- Fall back to a secondary provider if the primary is unavailable
- Validate provider connectivity before use

## Decision

Build the LLM provider abstraction on top of **LlamaIndex's existing provider system**, extended with:

1. **Unified configuration**: YAML-based config file (`config/providers.yaml`) with environment variable overrides for secrets
2. **Separate LLM and embedding provider configs**: inference and embedding are independently configurable
3. **Provider registry**: providers are registered by name and instantiated from config
4. **Health check interface**: each provider exposes a `health_check()` method
5. **Fallback chain**: ordered list of providers — if primary fails, try the next

### Supported Providers (v1)
- **AWS Bedrock** (default): `llama-index-llms-bedrock` / `llama-index-embeddings-bedrock`
- **OpenAI**: `llama-index-llms-openai` / `llama-index-embeddings-openai`
- **Ollama**: `llama-index-llms-ollama` / `llama-index-embeddings-ollama`
- **OpenRouter**: via OpenAI-compatible interface
- **LM Studio**: via OpenAI-compatible interface (local endpoint)

### Configuration Example

```yaml
llm:
  primary:
    provider: bedrock
    model: anthropic.claude-sonnet-4-20250514
    region: us-east-1
  fallback:
    provider: ollama
    model: llama3.1:13b
    base_url: http://localhost:11434

embeddings:
  primary:
    provider: bedrock
    model: amazon.titan-embed-text-v2
    region: us-east-1
  fallback:
    provider: ollama
    model: nomic-embed-text
    base_url: http://localhost:11434
```

## Consequences

### Positive
- Data sensitivity can be managed by routing through local models when needed
- LlamaIndex's provider packages are well-maintained and handle API specifics
- Adding new providers requires only a new config block and the corresponding LlamaIndex package
- Fallback chain provides resilience without manual intervention
- Separate embedding/LLM config allows cost optimization (cheap embeddings + powerful inference)

### Negative
- LlamaIndex provider packages add dependencies — each provider is a separate pip package
- OpenRouter and LM Studio use OpenAI-compatible mode, which may not support all features
- Fallback logic adds complexity to error handling paths
- Provider-specific features (e.g., Bedrock guardrails) are not exposed through the abstraction

### Risks
- LlamaIndex provider packages may lag behind upstream API changes
- Mitigation: the abstraction layer can be extended to bypass LlamaIndex for specific providers if needed
