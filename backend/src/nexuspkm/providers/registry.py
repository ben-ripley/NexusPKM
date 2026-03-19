"""Provider registry: instantiates, owns, and routes to LLM/embedding providers."""

from typing import Any

import structlog

from nexuspkm.config.models import (
    EmbeddingProviderConfig,
    LLMProviderConfig,
    ProvidersConfig,
)
from nexuspkm.providers.base import (
    BaseEmbeddingProvider,
    BaseLLMProvider,
    EmbeddingResponse,
    LLMResponse,
    ProviderError,
)

log = structlog.get_logger()


def _make_llm(config: LLMProviderConfig) -> BaseLLMProvider:
    provider = config.provider
    if provider == "bedrock":
        from nexuspkm.providers.bedrock import BedrockLLMProvider

        return BedrockLLMProvider(config)
    if provider in ("openai", "openrouter", "lm_studio"):
        from nexuspkm.providers.openai import OpenAILLMProvider

        return OpenAILLMProvider(config)
    if provider == "ollama":
        from nexuspkm.providers.ollama import OllamaLLMProvider

        return OllamaLLMProvider(config)
    raise ValueError(f"Unsupported LLM provider: {provider!r}")  # pragma: no cover


def _make_embedding(config: EmbeddingProviderConfig) -> BaseEmbeddingProvider:
    provider = config.provider
    if provider == "bedrock":
        from nexuspkm.providers.bedrock import BedrockEmbeddingProvider

        return BedrockEmbeddingProvider(config)
    if provider in ("openai", "lm_studio"):
        from nexuspkm.providers.openai import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider(config)
    if provider == "ollama":
        from nexuspkm.providers.ollama import OllamaEmbeddingProvider

        return OllamaEmbeddingProvider(config)
    raise ValueError(f"Unsupported embedding provider: {provider!r}")  # pragma: no cover


class ProviderRegistry:
    def __init__(self, config: ProvidersConfig) -> None:
        self._config = config
        self._llm_primary: BaseLLMProvider = _make_llm(config.llm.primary)
        self._llm_fallback: BaseLLMProvider | None = (
            _make_llm(config.llm.fallback) if config.llm.fallback else None
        )
        self._emb_primary: BaseEmbeddingProvider = _make_embedding(config.embedding.primary)
        self._emb_fallback: BaseEmbeddingProvider | None = (
            _make_embedding(config.embedding.fallback) if config.embedding.fallback else None
        )

    def get_llm(self) -> BaseLLMProvider:
        return self._llm_primary

    def get_embedding(self) -> BaseEmbeddingProvider:
        return self._emb_primary

    async def check_health(self) -> dict[str, Any]:
        llm_health = await self._llm_primary.health_check()
        emb_health = await self._emb_primary.health_check()
        result: dict[str, Any] = {"llm": llm_health, "embedding": emb_health}
        if self._llm_fallback:
            result["llm_fallback"] = await self._llm_fallback.health_check()
        if self._emb_fallback:
            result["embedding_fallback"] = await self._emb_fallback.health_check()
        return result

    async def generate_with_fallback(
        self, messages: list[dict[str, str]], **kwargs: object
    ) -> LLMResponse:
        try:
            return await self._llm_primary.generate(messages, **kwargs)
        except (ProviderError, Exception) as exc:
            if self._llm_fallback is None:
                raise
            log.warning(
                "llm_primary_failed_using_fallback",
                provider=self._config.llm.primary.provider,
                error=str(exc),
            )
            return await self._llm_fallback.generate(messages, **kwargs)

    async def embed_with_fallback(self, texts: list[str]) -> EmbeddingResponse:
        try:
            return await self._emb_primary.embed(texts)
        except (ProviderError, Exception) as exc:
            if self._emb_fallback is None:
                raise
            log.warning(
                "embedding_primary_failed_using_fallback",
                provider=self._config.embedding.primary.provider,
                error=str(exc),
            )
            return await self._emb_fallback.embed(texts)

    def reload(self, config: ProvidersConfig) -> None:
        self._config = config
        self._llm_primary = _make_llm(config.llm.primary)
        self._llm_fallback = _make_llm(config.llm.fallback) if config.llm.fallback else None
        self._emb_primary = _make_embedding(config.embedding.primary)
        self._emb_fallback = (
            _make_embedding(config.embedding.fallback) if config.embedding.fallback else None
        )
        log.info(
            "provider_registry_reloaded",
            llm_provider=config.llm.primary.provider,
            embedding_provider=config.embedding.primary.provider,
        )
