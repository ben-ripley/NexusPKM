"""Ollama LLM and embedding providers via LlamaIndex."""

import os
import time
from collections.abc import AsyncIterator
from typing import Any

import structlog

from nexuspkm.config.models import EmbeddingProviderConfig, LLMProviderConfig
from nexuspkm.providers._utils import extract_tokens, to_chat_messages
from nexuspkm.providers.base import (
    BaseEmbeddingProvider,
    BaseLLMProvider,
    EmbeddingResponse,
    LLMResponse,
    ProviderError,
    ProviderHealth,
)

log = structlog.get_logger()

try:
    from llama_index.llms.ollama import Ollama
except ImportError as exc:  # pragma: no cover
    raise ImportError("Install llama-index-llms-ollama to use the Ollama LLM provider") from exc

try:
    from llama_index.embeddings.ollama import OllamaEmbedding
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Install llama-index-embeddings-ollama to use the Ollama embedding provider"
    ) from exc

try:
    from llama_index.core.llms import ChatMessage, MessageRole
except ImportError as exc:  # pragma: no cover
    raise ImportError("Install llama-index-core to use providers") from exc

# Default base URL for Ollama. Override via the OLLAMA_BASE_URL environment variable
# or by setting base_url in config/providers.yaml.
_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


class OllamaLLMProvider(BaseLLMProvider):
    def __init__(self, config: LLMProviderConfig, *, _client: Any = None) -> None:
        self._config = config
        if _client is not None:
            self._client = _client
        else:
            self._client = Ollama(  # pragma: no cover
                model=config.model,
                base_url=config.base_url or _OLLAMA_BASE_URL,
                request_timeout=60.0,
            )

    async def generate(self, messages: list[dict[str, str]], **kwargs: object) -> LLMResponse:
        chat_messages = to_chat_messages(messages)
        try:
            response = await self._client.achat(chat_messages)
        except Exception as exc:
            log.error("ollama_llm_generate_failed", error=str(exc))
            raise ProviderError(str(exc)) from exc
        raw: dict[str, Any] = response.raw or {}
        input_tokens, output_tokens = extract_tokens(raw)
        return LLMResponse(
            content=response.message.content,
            provider="ollama",
            model=self._config.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def stream(self, messages: list[dict[str, str]], **kwargs: object) -> AsyncIterator[str]:
        chat_messages = to_chat_messages(messages)

        async def _gen() -> AsyncIterator[str]:
            try:
                async for chunk in self._client.astream_chat(chat_messages):
                    if chunk.delta:
                        yield chunk.delta
            except Exception as exc:
                log.error("ollama_llm_stream_failed", error=str(exc))
                raise ProviderError(str(exc)) from exc

        return _gen()

    async def health_check(self) -> ProviderHealth:
        start = time.monotonic()
        try:
            await self._client.achat([ChatMessage(role=MessageRole.USER, content="ping")])
            latency_ms = (time.monotonic() - start) * 1000
            return ProviderHealth(provider="ollama", status="healthy", latency_ms=latency_ms)
        except Exception as exc:
            return ProviderHealth(provider="ollama", status="unavailable", error=str(exc))


class OllamaEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(self, config: EmbeddingProviderConfig, *, _client: Any = None) -> None:
        self._config = config
        if _client is not None:
            self._client = _client
        else:
            self._client = OllamaEmbedding(  # pragma: no cover
                model_name=config.model,
                base_url=config.base_url or _OLLAMA_BASE_URL,
            )

    @property
    def dimension(self) -> int:
        return self._config.dimensions

    async def embed(self, texts: list[str]) -> EmbeddingResponse:
        try:
            vectors: list[list[float]] = await self._client.aget_text_embedding_batch(texts)
        except Exception as exc:
            log.error("ollama_embedding_failed", error=str(exc))
            raise ProviderError(str(exc)) from exc
        return EmbeddingResponse(
            embeddings=vectors,
            provider="ollama",
            model=self._config.model,
            dimensions=self._config.dimensions,
        )

    async def embed_single(self, text: str) -> list[float]:
        try:
            return list(await self._client.aget_text_embedding(text))
        except Exception as exc:
            log.error("ollama_embedding_single_failed", error=str(exc))
            raise ProviderError(str(exc)) from exc

    async def health_check(self) -> ProviderHealth:
        start = time.monotonic()
        try:
            await self._client.aget_text_embedding("health check")
            latency_ms = (time.monotonic() - start) * 1000
            return ProviderHealth(provider="ollama", status="healthy", latency_ms=latency_ms)
        except Exception as exc:
            return ProviderHealth(provider="ollama", status="unavailable", error=str(exc))
