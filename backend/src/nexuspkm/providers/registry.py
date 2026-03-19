"""Provider registry: instantiates, owns, and routes to LLM/embedding providers."""

import asyncio

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
    ProviderHealth,
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
        self._reload_lock: asyncio.Lock = asyncio.Lock()
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

    def active_config(self) -> dict[str, dict[str, str]]:
        return {
            "llm": {
                "provider": self._config.llm.primary.provider,
                "model": self._config.llm.primary.model,
            },
            "embedding": {
                "provider": self._config.embedding.primary.provider,
                "model": self._config.embedding.primary.model,
            },
        }

    async def check_health(self) -> dict[str, ProviderHealth]:
        llm_health = await self._llm_primary.health_check()
        emb_health = await self._emb_primary.health_check()
        result: dict[str, ProviderHealth] = {"llm": llm_health, "embedding": emb_health}
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
        except ProviderError as exc:
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
        except ProviderError as exc:
            if self._emb_fallback is None:
                raise
            log.warning(
                "embedding_primary_failed_using_fallback",
                provider=self._config.embedding.primary.provider,
                error=str(exc),
            )
            return await self._emb_fallback.embed(texts)

    async def reload(self, config: ProvidersConfig) -> None:
        new_llm_primary = _make_llm(config.llm.primary)
        new_llm_fallback = _make_llm(config.llm.fallback) if config.llm.fallback else None
        new_emb_primary = _make_embedding(config.embedding.primary)
        new_emb_fallback = (
            _make_embedding(config.embedding.fallback) if config.embedding.fallback else None
        )
        async with self._reload_lock:
            (
                self._config,
                self._llm_primary,
                self._llm_fallback,
                self._emb_primary,
                self._emb_fallback,
            ) = (config, new_llm_primary, new_llm_fallback, new_emb_primary, new_emb_fallback)
        log.info(
            "provider_registry_reloaded",
            llm_provider=config.llm.primary.provider,
            embedding_provider=config.embedding.primary.provider,
        )
