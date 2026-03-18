"""Pydantic configuration models for NexusPKM.

All models use BaseModel (not BaseSettings) — env var handling is done by
the loader so models remain pure data containers with no side effects.

Secrets (API keys, tokens) are intentionally absent from all models.
They are read directly from environment variables by provider implementations.
"""

from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

ProviderName = Literal["bedrock", "openai", "ollama", "openrouter", "lm_studio"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
LogFormat = Literal["json", "console"]


# ---------------------------------------------------------------------------
# Provider models
# ---------------------------------------------------------------------------


class LLMProviderConfig(BaseModel):
    provider: ProviderName
    model: str
    region: str | None = None
    base_url: str | None = None
    max_tokens: int = Field(default=4096, gt=0)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class EmbeddingProviderConfig(BaseModel):
    provider: ProviderName
    model: str
    region: str | None = None
    base_url: str | None = None
    dimensions: int = Field(default=1024, gt=0)


class LLMConfig(BaseModel):
    primary: LLMProviderConfig
    fallback: LLMProviderConfig | None = None


class EmbeddingConfig(BaseModel):
    primary: EmbeddingProviderConfig
    fallback: EmbeddingProviderConfig | None = None


class ProvidersConfig(BaseModel):
    llm: LLMConfig
    embedding: EmbeddingConfig


# ---------------------------------------------------------------------------
# App models
# ---------------------------------------------------------------------------


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, gt=0, le=65535)


class DataConfig(BaseModel):
    dir: str = "./data"


class LoggingConfig(BaseModel):
    level: LogLevel = "INFO"
    format: LogFormat = "json"


class ChunkingConfig(BaseModel):
    size: int = Field(default=512, gt=0)
    overlap: int = Field(default=50, ge=0)


class RetrievalConfig(BaseModel):
    vector_weight: float = Field(default=0.6, ge=0.0, le=1.0)
    graph_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    recency_weight: float = Field(default=0.1, ge=0.0, le=1.0)
    top_k: int = Field(default=10, gt=0)

    @model_validator(mode="after")
    def weights_must_sum_to_one(self) -> Self:
        total = self.vector_weight + self.graph_weight + self.recency_weight
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"vector_weight + graph_weight + recency_weight must equal 1.0, got {total}. "
                "When overriding weights via env vars, set all three together: "
                "NEXUSPKM_APP__RETRIEVAL__VECTOR_WEIGHT, "
                "NEXUSPKM_APP__RETRIEVAL__GRAPH_WEIGHT, "
                "NEXUSPKM_APP__RETRIEVAL__RECENCY_WEIGHT."
            )
        return self


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)


# ---------------------------------------------------------------------------
# Connector models
# ---------------------------------------------------------------------------


class TeamsConnectorConfig(BaseModel):
    enabled: bool = False
    sync_interval_minutes: int = Field(default=30, gt=0)


class OutlookConnectorConfig(BaseModel):
    enabled: bool = False
    sync_interval_minutes: int = Field(default=15, gt=0)
    folders: list[str] = Field(default_factory=lambda: ["Inbox", "Sent Items"])


class ObsidianConnectorConfig(BaseModel):
    enabled: bool = False
    # No default: vault path must be configured explicitly (platform-specific path)
    vault_path: Path | None = None
    sync_interval_minutes: int = Field(default=5, gt=0)
    exclude_patterns: list[str] = Field(
        default_factory=lambda: [".obsidian/", ".trash/", "templates/"]
    )

    @field_validator("vault_path", mode="before")
    @classmethod
    def expand_vault_path(cls, v: object) -> Path | None:
        if v is None:
            return None
        return Path(str(v)).expanduser()

    @model_validator(mode="after")
    def vault_path_required_when_enabled(self) -> Self:
        if self.enabled and not self.vault_path:
            raise ValueError("vault_path is required when obsidian connector is enabled")
        return self


class JiraConnectorConfig(BaseModel):
    enabled: bool = False
    base_url: str | None = None
    sync_interval_minutes: int = Field(default=30, gt=0)
    jql_filter: str = "assignee = currentUser() ORDER BY updated DESC"

    @model_validator(mode="after")
    def base_url_required_when_enabled(self) -> Self:
        if self.enabled and not self.base_url:
            raise ValueError("base_url is required when jira connector is enabled")
        return self


class AppleNotesConnectorConfig(BaseModel):
    enabled: bool = False
    sync_interval_minutes: int = Field(default=15, gt=0)


class ConnectorsConfig(BaseModel):
    teams: TeamsConnectorConfig = Field(default_factory=TeamsConnectorConfig)
    outlook: OutlookConnectorConfig = Field(default_factory=OutlookConnectorConfig)
    obsidian: ObsidianConnectorConfig = Field(default_factory=ObsidianConnectorConfig)
    jira: JiraConnectorConfig = Field(default_factory=JiraConnectorConfig)
    apple_notes: AppleNotesConnectorConfig = Field(default_factory=AppleNotesConnectorConfig)


# ---------------------------------------------------------------------------
# Top-level config
# ---------------------------------------------------------------------------


class NexusPKMConfig(BaseModel):
    providers: ProvidersConfig
    app: AppConfig = Field(default_factory=AppConfig)
    connectors: ConnectorsConfig = Field(default_factory=ConnectorsConfig)
