"""Unit tests for LLM and embedding provider abstraction layer (NXP-28)."""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexuspkm.config.models import EmbeddingProviderConfig, LLMProviderConfig, ProvidersConfig
from nexuspkm.providers.base import (
    BaseEmbeddingProvider,
    BaseLLMProvider,
    EmbeddingResponse,
    LLMResponse,
    ProviderError,
    ProviderHealth,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MESSAGES = [{"role": "user", "content": "Hello"}]

_LLM_CFG_BEDROCK = LLMProviderConfig(
    provider="bedrock", model="anthropic.claude-sonnet-4-20250514", region="us-east-1"
)
_LLM_CFG_OPENAI = LLMProviderConfig(provider="openai", model="gpt-4o")
_LLM_CFG_OPENROUTER = LLMProviderConfig(
    provider="openrouter",
    model="anthropic/claude-3.5-sonnet",
    base_url="https://openrouter.ai/api/v1",
)
_LLM_CFG_LMSTUDIO = LLMProviderConfig(
    provider="lm_studio",
    model="lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF",
    base_url="http://localhost:1234/v1",
)
_LLM_CFG_OLLAMA = LLMProviderConfig(
    provider="ollama", model="llama3.1:13b", base_url="http://localhost:11434"
)

_EMB_CFG_BEDROCK = EmbeddingProviderConfig(
    provider="bedrock", model="amazon.titan-embed-text-v2", region="us-east-1", dimensions=1024
)
_EMB_CFG_OPENAI = EmbeddingProviderConfig(
    provider="openai", model="text-embedding-3-small", dimensions=1536
)
_EMB_CFG_OLLAMA = EmbeddingProviderConfig(
    provider="ollama",
    model="nomic-embed-text",
    base_url="http://localhost:11434",
    dimensions=768,
)


def _make_providers_config(
    llm_primary: LLMProviderConfig = _LLM_CFG_BEDROCK,
    llm_fallback: LLMProviderConfig | None = None,
    emb_primary: EmbeddingProviderConfig = _EMB_CFG_BEDROCK,
    emb_fallback: EmbeddingProviderConfig | None = None,
) -> ProvidersConfig:
    from nexuspkm.config.models import EmbeddingConfig, LLMConfig

    return ProvidersConfig(
        llm=LLMConfig(primary=llm_primary, fallback=llm_fallback),
        embedding=EmbeddingConfig(primary=emb_primary, fallback=emb_fallback),
    )


def _mock_llm_client(
    content: str = "Hello!", input_tokens: int = 10, output_tokens: int = 5
) -> MagicMock:
    """Return a mock LlamaIndex LLM with achat and astream_chat configured."""
    mock = MagicMock()
    chat_response = MagicMock()
    chat_response.message.content = content
    chat_response.raw = {"usage": {"inputTokens": input_tokens, "outputTokens": output_tokens}}
    mock.achat = AsyncMock(return_value=chat_response)

    async def _stream(*args: Any, **kwargs: Any) -> AsyncIterator[MagicMock]:
        for word in content.split():
            chunk = MagicMock()
            chunk.delta = word + " "
            yield chunk

    mock.astream_chat = _stream
    return mock


def _mock_embed_client(dims: int = 1024) -> MagicMock:
    """Return a mock LlamaIndex embedding model."""
    mock = MagicMock()
    vec = [0.1] * dims
    mock.aget_text_embedding_batch = AsyncMock(return_value=[vec, vec])
    mock.aget_text_embedding = AsyncMock(return_value=vec)
    return mock


# ---------------------------------------------------------------------------
# base.py — models and ABCs
# ---------------------------------------------------------------------------


class TestProviderHealth:
    def test_constructs_minimal(self) -> None:
        h = ProviderHealth(provider="bedrock", status="healthy")
        assert h.provider == "bedrock"
        assert h.status == "healthy"
        assert h.latency_ms is None
        assert h.error is None

    def test_constructs_full(self) -> None:
        h = ProviderHealth(
            provider="openai", status="unavailable", latency_ms=123.4, error="timeout"
        )
        assert h.latency_ms == 123.4
        assert h.error == "timeout"

    def test_invalid_status(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ProviderHealth(provider="x", status="unknown")  # type: ignore[arg-type]


class TestLLMResponse:
    def test_constructs(self) -> None:
        r = LLMResponse(
            content="hi", provider="bedrock", model="claude-3", input_tokens=5, output_tokens=3
        )
        assert r.content == "hi"
        assert r.input_tokens == 5
        assert r.output_tokens == 3


class TestEmbeddingResponse:
    def test_constructs(self) -> None:
        r = EmbeddingResponse(
            embeddings=[[0.1, 0.2], [0.3, 0.4]], provider="bedrock", model="titan", dimensions=2
        )
        assert len(r.embeddings) == 2
        assert r.dimensions == 2


class TestAbstractClasses:
    def test_llm_provider_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            BaseLLMProvider()  # type: ignore[abstract]

    def test_embedding_provider_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            BaseEmbeddingProvider()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# BedrockLLMProvider
# ---------------------------------------------------------------------------


class TestBedrockLLMProvider:
    def _make(self, cfg: LLMProviderConfig = _LLM_CFG_BEDROCK) -> "Any":
        from nexuspkm.providers.bedrock import BedrockLLMProvider

        return BedrockLLMProvider(cfg, _client=_mock_llm_client())

    def test_constructs(self) -> None:
        p = self._make()
        assert p is not None

    async def test_generate_returns_llm_response(self) -> None:
        from nexuspkm.providers.bedrock import BedrockLLMProvider

        mock_client = _mock_llm_client("Hello!", 10, 5)
        p = BedrockLLMProvider(_LLM_CFG_BEDROCK, _client=mock_client)
        result = await p.generate(_MESSAGES)
        assert isinstance(result, LLMResponse)
        assert result.content == "Hello!"
        assert result.provider == "bedrock"
        assert result.input_tokens == 10
        assert result.output_tokens == 5

    async def test_stream_yields_chunks(self) -> None:
        from nexuspkm.providers.bedrock import BedrockLLMProvider

        mock_client = _mock_llm_client("Hello World")
        p = BedrockLLMProvider(_LLM_CFG_BEDROCK, _client=mock_client)
        chunks = []
        async for chunk in await p.stream(_MESSAGES):
            chunks.append(chunk)
        assert len(chunks) > 0
        assert "".join(chunks).strip()

    async def test_stream_raises_provider_error_on_exception(self) -> None:
        from nexuspkm.providers.bedrock import BedrockLLMProvider

        async def _failing_stream(*args: Any, **kwargs: Any) -> AsyncIterator[MagicMock]:
            raise Exception("stream failure")
            yield  # make it an async generator

        mock_client = MagicMock()
        mock_client.astream_chat = _failing_stream
        p = BedrockLLMProvider(_LLM_CFG_BEDROCK, _client=mock_client)
        with pytest.raises(ProviderError):
            async for _ in await p.stream(_MESSAGES):
                pass

    async def test_health_check_healthy(self) -> None:
        from nexuspkm.providers.bedrock import BedrockLLMProvider

        mock_client = _mock_llm_client()
        p = BedrockLLMProvider(_LLM_CFG_BEDROCK, _client=mock_client)
        health = await p.health_check()
        assert isinstance(health, ProviderHealth)
        assert health.status == "healthy"
        assert health.latency_ms is not None

    async def test_health_check_unavailable_on_error(self) -> None:
        from nexuspkm.providers.bedrock import BedrockLLMProvider

        mock_client = MagicMock()
        mock_client.achat = AsyncMock(side_effect=Exception("connection refused"))
        p = BedrockLLMProvider(_LLM_CFG_BEDROCK, _client=mock_client)
        health = await p.health_check()
        assert health.status == "unavailable"
        assert health.error is not None

    async def test_generate_raises_provider_error_on_exception(self) -> None:
        from nexuspkm.providers.bedrock import BedrockLLMProvider

        mock_client = MagicMock()
        mock_client.achat = AsyncMock(side_effect=Exception("bedrock failure"))
        p = BedrockLLMProvider(_LLM_CFG_BEDROCK, _client=mock_client)
        with pytest.raises(ProviderError):
            await p.generate(_MESSAGES)


# ---------------------------------------------------------------------------
# BedrockEmbeddingProvider
# ---------------------------------------------------------------------------


class TestBedrockEmbeddingProvider:
    def _make(self, cfg: EmbeddingProviderConfig = _EMB_CFG_BEDROCK) -> "Any":
        from nexuspkm.providers.bedrock import BedrockEmbeddingProvider

        return BedrockEmbeddingProvider(cfg, _client=_mock_embed_client(cfg.dimensions))

    def test_constructs(self) -> None:
        p = self._make()
        assert p is not None

    def test_dimension_property(self) -> None:
        p = self._make()
        assert p.dimension == 1024

    async def test_embed_returns_embedding_response(self) -> None:
        from nexuspkm.providers.bedrock import BedrockEmbeddingProvider

        mock_client = _mock_embed_client(1024)
        p = BedrockEmbeddingProvider(_EMB_CFG_BEDROCK, _client=mock_client)
        result = await p.embed(["hello", "world"])
        assert isinstance(result, EmbeddingResponse)
        assert len(result.embeddings) == 2
        assert result.dimensions == 1024
        assert result.provider == "bedrock"

    async def test_embed_single_returns_vector(self) -> None:
        from nexuspkm.providers.bedrock import BedrockEmbeddingProvider

        mock_client = _mock_embed_client(1024)
        p = BedrockEmbeddingProvider(_EMB_CFG_BEDROCK, _client=mock_client)
        vec = await p.embed_single("hello")
        assert isinstance(vec, list)
        assert len(vec) == 1024

    async def test_health_check_healthy(self) -> None:
        from nexuspkm.providers.bedrock import BedrockEmbeddingProvider

        mock_client = _mock_embed_client(1024)
        p = BedrockEmbeddingProvider(_EMB_CFG_BEDROCK, _client=mock_client)
        health = await p.health_check()
        assert health.status == "healthy"

    async def test_health_check_unavailable_on_error(self) -> None:
        from nexuspkm.providers.bedrock import BedrockEmbeddingProvider

        mock_client = MagicMock()
        mock_client.aget_text_embedding = AsyncMock(side_effect=Exception("auth error"))
        p = BedrockEmbeddingProvider(_EMB_CFG_BEDROCK, _client=mock_client)
        health = await p.health_check()
        assert health.status == "unavailable"
        assert health.error is not None


# ---------------------------------------------------------------------------
# OpenAILLMProvider
# ---------------------------------------------------------------------------


class TestOpenAILLMProvider:
    def _make(self, cfg: LLMProviderConfig = _LLM_CFG_OPENAI) -> "Any":
        from nexuspkm.providers.openai import OpenAILLMProvider

        mock_client = _mock_llm_client()
        mock_client.achat.return_value.raw = {"usage": {"prompt_tokens": 8, "completion_tokens": 4}}
        return OpenAILLMProvider(cfg, _client=mock_client)

    def test_constructs_no_base_url(self) -> None:
        p = self._make(_LLM_CFG_OPENAI)
        assert p is not None

    def test_constructs_with_base_url_openrouter(self) -> None:
        p = self._make(_LLM_CFG_OPENROUTER)
        assert p is not None

    def test_constructs_with_base_url_lmstudio(self) -> None:
        p = self._make(_LLM_CFG_LMSTUDIO)
        assert p is not None

    async def test_generate_returns_llm_response(self) -> None:
        from nexuspkm.providers.openai import OpenAILLMProvider

        mock_client = _mock_llm_client("Hi!", 8, 4)
        mock_client.achat.return_value.raw = {"usage": {"prompt_tokens": 8, "completion_tokens": 4}}
        p = OpenAILLMProvider(_LLM_CFG_OPENAI, _client=mock_client)
        result = await p.generate(_MESSAGES)
        assert isinstance(result, LLMResponse)
        assert result.content == "Hi!"
        assert result.provider == "openai"

    async def test_health_check_healthy(self) -> None:

        p = self._make()
        health = await p.health_check()
        assert health.status == "healthy"

    async def test_stream_yields_chunks(self) -> None:
        from nexuspkm.providers.openai import OpenAILLMProvider

        mock_client = _mock_llm_client("Hi there")
        p = OpenAILLMProvider(_LLM_CFG_OPENAI, _client=mock_client)
        chunks = []
        async for chunk in await p.stream(_MESSAGES):
            chunks.append(chunk)
        assert len(chunks) > 0

    async def test_stream_raises_provider_error_on_exception(self) -> None:
        from nexuspkm.providers.openai import OpenAILLMProvider

        async def _failing_stream(*args: Any, **kwargs: Any) -> AsyncIterator[MagicMock]:
            raise Exception("stream failure")
            yield  # make it an async generator

        mock_client = MagicMock()
        mock_client.astream_chat = _failing_stream
        p = OpenAILLMProvider(_LLM_CFG_OPENAI, _client=mock_client)
        with pytest.raises(ProviderError):
            async for _ in await p.stream(_MESSAGES):
                pass

    async def test_health_check_unavailable(self) -> None:
        from nexuspkm.providers.openai import OpenAILLMProvider

        mock_client = MagicMock()
        mock_client.achat = AsyncMock(side_effect=Exception("auth error"))
        p = OpenAILLMProvider(_LLM_CFG_OPENAI, _client=mock_client)
        health = await p.health_check()
        assert health.status == "unavailable"


# ---------------------------------------------------------------------------
# OpenAIEmbeddingProvider
# ---------------------------------------------------------------------------


class TestOpenAIEmbeddingProvider:
    def _make(self, cfg: EmbeddingProviderConfig = _EMB_CFG_OPENAI) -> "Any":
        from nexuspkm.providers.openai import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider(cfg, _client=_mock_embed_client(cfg.dimensions))

    def test_constructs(self) -> None:
        p = self._make()
        assert p is not None

    def test_dimension_property(self) -> None:
        p = self._make()
        assert p.dimension == 1536

    async def test_embed_returns_response(self) -> None:
        from nexuspkm.providers.openai import OpenAIEmbeddingProvider

        mock_client = _mock_embed_client(1536)
        p = OpenAIEmbeddingProvider(_EMB_CFG_OPENAI, _client=mock_client)
        result = await p.embed(["hello", "world"])
        assert isinstance(result, EmbeddingResponse)
        assert len(result.embeddings) == 2
        assert result.dimensions == 1536

    async def test_embed_single_returns_vector(self) -> None:
        from nexuspkm.providers.openai import OpenAIEmbeddingProvider

        mock_client = _mock_embed_client(1536)
        p = OpenAIEmbeddingProvider(_EMB_CFG_OPENAI, _client=mock_client)
        vec = await p.embed_single("hello")
        assert len(vec) == 1536

    async def test_health_check_healthy(self) -> None:

        p = self._make()
        health = await p.health_check()
        assert health.status == "healthy"


# ---------------------------------------------------------------------------
# OllamaLLMProvider
# ---------------------------------------------------------------------------


class TestOllamaLLMProvider:
    def _make(self, cfg: LLMProviderConfig = _LLM_CFG_OLLAMA) -> "Any":
        from nexuspkm.providers.ollama import OllamaLLMProvider

        return OllamaLLMProvider(cfg, _client=_mock_llm_client())

    def test_constructs(self) -> None:
        p = self._make()
        assert p is not None

    async def test_generate_returns_llm_response(self) -> None:
        from nexuspkm.providers.ollama import OllamaLLMProvider

        mock_client = _mock_llm_client("Yo!")
        p = OllamaLLMProvider(_LLM_CFG_OLLAMA, _client=mock_client)
        result = await p.generate(_MESSAGES)
        assert isinstance(result, LLMResponse)
        assert result.content == "Yo!"
        assert result.provider == "ollama"

    async def test_health_check_healthy(self) -> None:

        p = self._make()
        health = await p.health_check()
        assert health.status == "healthy"

    async def test_stream_yields_chunks(self) -> None:
        from nexuspkm.providers.ollama import OllamaLLMProvider

        mock_client = _mock_llm_client("Hey there")
        p = OllamaLLMProvider(_LLM_CFG_OLLAMA, _client=mock_client)
        chunks = []
        async for chunk in await p.stream(_MESSAGES):
            chunks.append(chunk)
        assert len(chunks) > 0

    async def test_stream_raises_provider_error_on_exception(self) -> None:
        from nexuspkm.providers.ollama import OllamaLLMProvider

        async def _failing_stream(*args: Any, **kwargs: Any) -> AsyncIterator[MagicMock]:
            raise Exception("stream failure")
            yield  # make it an async generator

        mock_client = MagicMock()
        mock_client.astream_chat = _failing_stream
        p = OllamaLLMProvider(_LLM_CFG_OLLAMA, _client=mock_client)
        with pytest.raises(ProviderError):
            async for _ in await p.stream(_MESSAGES):
                pass

    async def test_health_check_unavailable(self) -> None:
        from nexuspkm.providers.ollama import OllamaLLMProvider

        mock_client = MagicMock()
        mock_client.achat = AsyncMock(side_effect=Exception("connection refused"))
        p = OllamaLLMProvider(_LLM_CFG_OLLAMA, _client=mock_client)
        health = await p.health_check()
        assert health.status == "unavailable"


# ---------------------------------------------------------------------------
# OllamaEmbeddingProvider
# ---------------------------------------------------------------------------


class TestOllamaEmbeddingProvider:
    def _make(self, cfg: EmbeddingProviderConfig = _EMB_CFG_OLLAMA) -> "Any":
        from nexuspkm.providers.ollama import OllamaEmbeddingProvider

        return OllamaEmbeddingProvider(cfg, _client=_mock_embed_client(cfg.dimensions))

    def test_constructs(self) -> None:
        p = self._make()
        assert p is not None

    def test_dimension_property(self) -> None:
        p = self._make()
        assert p.dimension == 768

    async def test_embed_returns_response(self) -> None:
        from nexuspkm.providers.ollama import OllamaEmbeddingProvider

        mock_client = _mock_embed_client(768)
        p = OllamaEmbeddingProvider(_EMB_CFG_OLLAMA, _client=mock_client)
        result = await p.embed(["hello"])
        assert isinstance(result, EmbeddingResponse)
        assert result.dimensions == 768
        assert result.provider == "ollama"

    async def test_embed_single_returns_vector(self) -> None:
        from nexuspkm.providers.ollama import OllamaEmbeddingProvider

        mock_client = _mock_embed_client(768)
        p = OllamaEmbeddingProvider(_EMB_CFG_OLLAMA, _client=mock_client)
        vec = await p.embed_single("hello")
        assert len(vec) == 768

    async def test_health_check_healthy(self) -> None:

        p = self._make()
        health = await p.health_check()
        assert health.status == "healthy"


# ---------------------------------------------------------------------------
# ProviderRegistry
# ---------------------------------------------------------------------------


def _patched_registry(
    llm_primary: LLMProviderConfig = _LLM_CFG_BEDROCK,
    llm_fallback: LLMProviderConfig | None = None,
    emb_primary: EmbeddingProviderConfig = _EMB_CFG_BEDROCK,
    emb_fallback: EmbeddingProviderConfig | None = None,
) -> "Any":
    """Build a ProviderRegistry with all LlamaIndex clients mocked out."""
    from nexuspkm.providers.registry import ProviderRegistry

    cfg = _make_providers_config(llm_primary, llm_fallback, emb_primary, emb_fallback)
    with (
        patch("nexuspkm.providers.bedrock.Bedrock", return_value=_mock_llm_client()),
        patch("nexuspkm.providers.bedrock.BedrockEmbedding", return_value=_mock_embed_client(1024)),
        patch("nexuspkm.providers.openai.OpenAI", return_value=_mock_llm_client()),
        patch("nexuspkm.providers.openai.OpenAIEmbedding", return_value=_mock_embed_client(1536)),
        patch("nexuspkm.providers.ollama.Ollama", return_value=_mock_llm_client()),
        patch("nexuspkm.providers.ollama.OllamaEmbedding", return_value=_mock_embed_client(768)),
    ):
        return ProviderRegistry(cfg)


class TestProviderRegistry:
    def test_constructs(self) -> None:
        reg = _patched_registry()
        assert reg is not None

    def test_get_llm_returns_base_llm_provider(self) -> None:
        reg = _patched_registry()
        llm = reg.get_llm()
        assert isinstance(llm, BaseLLMProvider)

    def test_get_embedding_returns_base_embedding_provider(self) -> None:
        reg = _patched_registry()
        emb = reg.get_embedding()
        assert isinstance(emb, BaseEmbeddingProvider)

    async def test_check_health_returns_dict_with_keys(self) -> None:
        reg = _patched_registry()
        health = await reg.check_health()
        assert "llm" in health
        assert "embedding" in health

    async def test_generate_with_fallback_primary_succeeds(self) -> None:
        reg = _patched_registry()
        # Replace primary LLM with a controlled mock
        mock_client = _mock_llm_client("success")
        from nexuspkm.providers.bedrock import BedrockLLMProvider

        reg._llm_primary = BedrockLLMProvider(_LLM_CFG_BEDROCK, _client=mock_client)
        result = await reg.generate_with_fallback(_MESSAGES)
        assert isinstance(result, LLMResponse)
        assert result.content == "success"

    async def test_generate_with_fallback_uses_fallback_on_primary_failure(self) -> None:
        from nexuspkm.providers.bedrock import BedrockLLMProvider
        from nexuspkm.providers.ollama import OllamaLLMProvider

        reg = _patched_registry(llm_fallback=_LLM_CFG_OLLAMA)

        # Primary always fails
        fail_client = MagicMock()
        fail_client.achat = AsyncMock(side_effect=Exception("primary down"))
        reg._llm_primary = BedrockLLMProvider(_LLM_CFG_BEDROCK, _client=fail_client)

        # Fallback succeeds
        ok_client = _mock_llm_client("fallback response")
        reg._llm_fallback = OllamaLLMProvider(_LLM_CFG_OLLAMA, _client=ok_client)

        result = await reg.generate_with_fallback(_MESSAGES)
        assert result.content == "fallback response"

    async def test_generate_with_fallback_raises_when_no_fallback(self) -> None:
        from nexuspkm.providers.bedrock import BedrockLLMProvider

        reg = _patched_registry()
        fail_client = MagicMock()
        fail_client.achat = AsyncMock(side_effect=Exception("primary down"))
        reg._llm_primary = BedrockLLMProvider(_LLM_CFG_BEDROCK, _client=fail_client)
        reg._llm_fallback = None

        with pytest.raises(ProviderError):
            await reg.generate_with_fallback(_MESSAGES)

    async def test_embed_with_fallback_primary_succeeds(self) -> None:
        reg = _patched_registry()
        mock_client = _mock_embed_client(1024)
        from nexuspkm.providers.bedrock import BedrockEmbeddingProvider

        reg._emb_primary = BedrockEmbeddingProvider(_EMB_CFG_BEDROCK, _client=mock_client)
        result = await reg.embed_with_fallback(["hello"])
        assert isinstance(result, EmbeddingResponse)

    async def test_embed_with_fallback_uses_fallback_on_primary_failure(self) -> None:
        from nexuspkm.providers.bedrock import BedrockEmbeddingProvider
        from nexuspkm.providers.ollama import OllamaEmbeddingProvider

        reg = _patched_registry(emb_fallback=_EMB_CFG_OLLAMA)

        fail_client = MagicMock()
        fail_client.aget_text_embedding_batch = AsyncMock(side_effect=Exception("primary down"))
        reg._emb_primary = BedrockEmbeddingProvider(_EMB_CFG_BEDROCK, _client=fail_client)

        ok_client = _mock_embed_client(768)
        reg._emb_fallback = OllamaEmbeddingProvider(_EMB_CFG_OLLAMA, _client=ok_client)

        result = await reg.embed_with_fallback(["hello"])
        assert isinstance(result, EmbeddingResponse)

    async def test_embed_with_fallback_raises_when_no_fallback(self) -> None:
        from nexuspkm.providers.bedrock import BedrockEmbeddingProvider

        reg = _patched_registry()
        fail_client = MagicMock()
        fail_client.aget_text_embedding_batch = AsyncMock(side_effect=Exception("primary down"))
        reg._emb_primary = BedrockEmbeddingProvider(_EMB_CFG_BEDROCK, _client=fail_client)
        reg._emb_fallback = None

        with pytest.raises(ProviderError):
            await reg.embed_with_fallback(["hello"])

    async def test_reload_replaces_providers(self) -> None:
        from nexuspkm.providers.registry import ProviderRegistry

        cfg = _make_providers_config()
        with (
            patch("nexuspkm.providers.bedrock.Bedrock", return_value=_mock_llm_client()),
            patch(
                "nexuspkm.providers.bedrock.BedrockEmbedding",
                return_value=_mock_embed_client(1024),
            ),
        ):
            reg = ProviderRegistry(cfg)
            old_llm = reg.get_llm()

        new_cfg = _make_providers_config()
        with (
            patch("nexuspkm.providers.bedrock.Bedrock", return_value=_mock_llm_client()),
            patch(
                "nexuspkm.providers.bedrock.BedrockEmbedding",
                return_value=_mock_embed_client(1024),
            ),
        ):
            await reg.reload(new_cfg)
            new_llm = reg.get_llm()

        # After reload we get a new provider instance
        assert new_llm is not old_llm


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


def _build_test_app() -> "Any":
    """Build a FastAPI test app with a mocked ProviderRegistry."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from nexuspkm.api.providers import get_registry, router

    mock_registry = MagicMock()
    mock_registry.check_health = AsyncMock(
        return_value={
            "llm": ProviderHealth(provider="bedrock", status="healthy", latency_ms=50.0),
            "embedding": ProviderHealth(provider="bedrock", status="healthy", latency_ms=30.0),
        }
    )
    mock_registry.active_config = MagicMock(
        return_value={
            "llm": {"provider": "bedrock", "model": "anthropic.claude-sonnet-4-20250514"},
            "embedding": {"provider": "bedrock", "model": "amazon.titan-embed-text-v2"},
        }
    )
    mock_registry.reload = AsyncMock()

    test_app = FastAPI()
    test_app.include_router(router)
    test_app.dependency_overrides[get_registry] = lambda: mock_registry

    return TestClient(test_app), mock_registry


class TestProviderAPIEndpoints:
    def test_get_health_returns_200(self) -> None:
        client, _ = _build_test_app()
        resp = client.get("/api/providers/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "llm" in data
        assert "embedding" in data

    def test_get_active_returns_200(self) -> None:
        client, _ = _build_test_app()
        resp = client.get("/api/providers/active")
        assert resp.status_code == 200
        data = resp.json()
        assert "llm" in data
        assert "embedding" in data
        assert data["llm"]["provider"] == "bedrock"
        assert data["embedding"]["provider"] == "bedrock"

    def test_put_config_valid_returns_200(self) -> None:
        client, _ = _build_test_app()
        payload = {
            "llm": {
                "primary": {"provider": "openai", "model": "gpt-4o"},
            },
            "embedding": {
                "primary": {"provider": "openai", "model": "text-embedding-3-small"},
            },
        }
        with (
            patch("nexuspkm.providers.openai.OpenAI", return_value=_mock_llm_client()),
            patch(
                "nexuspkm.providers.openai.OpenAIEmbedding", return_value=_mock_embed_client(1536)
            ),
        ):
            resp = client.put("/api/providers/config", json=payload)
        assert resp.status_code == 200

    def test_put_config_invalid_returns_422(self) -> None:
        client, _ = _build_test_app()
        resp = client.put("/api/providers/config", json={"bad": "data"})
        assert resp.status_code == 422

    def test_put_config_returns_500_when_reload_raises(self) -> None:
        client, mock_registry = _build_test_app()
        mock_registry.reload = AsyncMock(side_effect=RuntimeError("provider init failed"))
        payload = {
            "llm": {"primary": {"provider": "openai", "model": "gpt-4o"}},
            "embedding": {"primary": {"provider": "openai", "model": "text-embedding-3-small"}},
        }
        resp = client.put("/api/providers/config", json=payload)
        assert resp.status_code == 500
