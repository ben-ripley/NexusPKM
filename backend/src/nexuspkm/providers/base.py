"""Abstract base classes and shared response models for LLM/embedding providers."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Literal

from pydantic import BaseModel


class ProviderHealth(BaseModel):
    provider: str
    status: Literal["healthy", "degraded", "unavailable"]
    latency_ms: float | None = None
    error: str | None = None


class LLMResponse(BaseModel):
    content: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


class EmbeddingResponse(BaseModel):
    embeddings: list[list[float]]
    provider: str
    model: str
    dimensions: int


class ProviderError(Exception):
    """Raised when a provider call fails in a way that should trigger fallback."""


class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate(self, messages: list[dict[str, str]], **kwargs: object) -> LLMResponse: ...

    @abstractmethod
    async def stream(
        self, messages: list[dict[str, str]], **kwargs: object
    ) -> AsyncIterator[str]: ...

    @abstractmethod
    async def health_check(self) -> ProviderHealth: ...


class BaseEmbeddingProvider(ABC):
    @property
    @abstractmethod
    def dimension(self) -> int: ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> EmbeddingResponse: ...

    @abstractmethod
    async def embed_single(self, text: str) -> list[float]: ...

    @abstractmethod
    async def health_check(self) -> ProviderHealth: ...
