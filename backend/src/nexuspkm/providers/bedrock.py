"""AWS Bedrock LLM and embedding providers via LlamaIndex."""

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
    from llama_index.llms.bedrock import Bedrock
except ImportError as exc:  # pragma: no cover
    raise ImportError("Install llama-index-llms-bedrock to use the Bedrock LLM provider") from exc

try:
    from llama_index.embeddings.bedrock import BedrockEmbedding
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Install llama-index-embeddings-bedrock to use the Bedrock embedding provider"
    ) from exc

try:
    from llama_index.core.llms import ChatMessage, MessageRole
except ImportError as exc:  # pragma: no cover
    raise ImportError("Install llama-index-core to use providers") from exc


class BedrockLLMProvider(BaseLLMProvider):
    def __init__(self, config: LLMProviderConfig, *, _client: Any = None) -> None:
        self._config = config
        if _client is not None:
            self._client = _client
        else:
            self._client = Bedrock(  # pragma: no cover
                model=config.model,
                region_name=config.region or "us-east-1",
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )

    async def generate(self, messages: list[dict[str, str]], **kwargs: object) -> LLMResponse:
        chat_messages = to_chat_messages(messages)
        try:
            response = await self._client.achat(chat_messages)
        except Exception as exc:
            log.error("bedrock_llm_generate_failed", error=str(exc))
            raise ProviderError(str(exc)) from exc
        raw: dict[str, Any] = response.raw or {}
        input_tokens, output_tokens = extract_tokens(raw)
        return LLMResponse(
            content=response.message.content,
            provider="bedrock",
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
                log.error("bedrock_llm_stream_failed", error=str(exc))
                raise ProviderError(str(exc)) from exc

        return _gen()

    async def health_check(self) -> ProviderHealth:
        start = time.monotonic()
        try:
            await self._client.achat([ChatMessage(role=MessageRole.USER, content="ping")])
            latency_ms = (time.monotonic() - start) * 1000
            return ProviderHealth(provider="bedrock", status="healthy", latency_ms=latency_ms)
        except Exception as exc:
            return ProviderHealth(provider="bedrock", status="unavailable", error=str(exc))


class BedrockEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(self, config: EmbeddingProviderConfig, *, _client: Any = None) -> None:
        self._config = config
        if _client is not None:
            self._client = _client
        else:
            self._client = BedrockEmbedding(  # pragma: no cover
                model_name=config.model,
                region_name=config.region or "us-east-1",
            )

    @property
    def dimension(self) -> int:
        return self._config.dimensions

    async def embed(self, texts: list[str]) -> EmbeddingResponse:
        try:
            vectors: list[list[float]] = await self._client.aget_text_embedding_batch(texts)
        except Exception as exc:
            log.error("bedrock_embedding_failed", error=str(exc))
            raise ProviderError(str(exc)) from exc
        return EmbeddingResponse(
            embeddings=vectors,
            provider="bedrock",
            model=self._config.model,
            dimensions=self._config.dimensions,
        )

    async def embed_single(self, text: str) -> list[float]:
        try:
            return list(await self._client.aget_text_embedding(text))
        except Exception as exc:
            log.error("bedrock_embedding_single_failed", error=str(exc))
            raise ProviderError(str(exc)) from exc

    async def health_check(self) -> ProviderHealth:
        start = time.monotonic()
        try:
            await self._client.aget_text_embedding("health check")
            latency_ms = (time.monotonic() - start) * 1000
            return ProviderHealth(provider="bedrock", status="healthy", latency_ms=latency_ms)
        except Exception as exc:
            return ProviderHealth(provider="bedrock", status="unavailable", error=str(exc))
