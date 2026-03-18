"""Tests for the configuration loading system (NXP-29)."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from nexuspkm.config import load_config
from nexuspkm.config.models import (
    EmbeddingProviderConfig,
    JiraConnectorConfig,
    LLMProviderConfig,
    NexusPKMConfig,
    OutlookConnectorConfig,
    TeamsConnectorConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMAL_PROVIDERS = {
    "llm": {
        "primary": {
            "provider": "bedrock",
            "model": "us.anthropic.claude-sonnet-4-6",
            "region": "us-east-1",
        }
    },
    "embedding": {
        "primary": {
            "provider": "bedrock",
            "model": "amazon.titan-embed-text-v2:0",
            "region": "us-east-1",
        }
    },
}

FULL_PROVIDERS = {
    "llm": {
        "primary": {
            "provider": "bedrock",
            "model": "us.anthropic.claude-sonnet-4-6",
            "region": "us-east-1",
            "max_tokens": 8192,
            "temperature": 0.5,
        },
        "fallback": {
            "provider": "ollama",
            "model": "llama3.2",
            "base_url": "http://localhost:11434",
        },
    },
    "embedding": {
        "primary": {
            "provider": "bedrock",
            "model": "amazon.titan-embed-text-v2:0",
            "region": "us-east-1",
            "dimensions": 1024,
        },
        "fallback": {
            "provider": "ollama",
            "model": "nomic-embed-text",
            "base_url": "http://localhost:11434",
        },
    },
}


def write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.dump(data))


# ---------------------------------------------------------------------------
# load_config — valid YAML
# ---------------------------------------------------------------------------


def test_load_config_returns_nexuspkm_config(tmp_path: Path) -> None:
    write_yaml(tmp_path / "providers.yaml", MINIMAL_PROVIDERS)
    config = load_config(tmp_path)
    assert isinstance(config, NexusPKMConfig)


def test_load_config_providers_llm_primary(tmp_path: Path) -> None:
    write_yaml(tmp_path / "providers.yaml", FULL_PROVIDERS)
    config = load_config(tmp_path)
    assert config.providers.llm.primary.provider == "bedrock"
    assert config.providers.llm.primary.model == "us.anthropic.claude-sonnet-4-6"
    assert config.providers.llm.primary.region == "us-east-1"
    assert config.providers.llm.primary.max_tokens == 8192
    assert config.providers.llm.primary.temperature == 0.5


def test_load_config_providers_llm_fallback(tmp_path: Path) -> None:
    write_yaml(tmp_path / "providers.yaml", FULL_PROVIDERS)
    config = load_config(tmp_path)
    assert config.providers.llm.fallback is not None
    assert config.providers.llm.fallback.provider == "ollama"
    assert config.providers.llm.fallback.base_url == "http://localhost:11434"


def test_load_config_providers_embedding(tmp_path: Path) -> None:
    write_yaml(tmp_path / "providers.yaml", FULL_PROVIDERS)
    config = load_config(tmp_path)
    assert config.providers.embedding.primary.provider == "bedrock"
    assert config.providers.embedding.primary.dimensions == 1024


def test_load_config_app_settings(tmp_path: Path) -> None:
    write_yaml(tmp_path / "providers.yaml", MINIMAL_PROVIDERS)
    write_yaml(
        tmp_path / "app.yaml",
        {
            "server": {"host": "0.0.0.0", "port": 9000},
            "logging": {"level": "DEBUG", "format": "console"},
            "chunking": {"size": 256, "overlap": 25},
            "retrieval": {"top_k": 20},
        },
    )
    config = load_config(tmp_path)
    assert config.app.server.host == "0.0.0.0"
    assert config.app.server.port == 9000
    assert config.app.logging.level == "DEBUG"
    assert config.app.chunking.size == 256
    assert config.app.retrieval.top_k == 20


def test_load_config_connectors(tmp_path: Path) -> None:
    write_yaml(tmp_path / "providers.yaml", MINIMAL_PROVIDERS)
    write_yaml(
        tmp_path / "connectors.yaml",
        {
            "obsidian": {"enabled": True, "vault_path": "~/Notes"},
            "teams": {"enabled": False},
        },
    )
    config = load_config(tmp_path)
    assert config.connectors.obsidian.enabled is True
    assert config.connectors.obsidian.vault_path == "~/Notes"
    assert config.connectors.teams.enabled is False


# ---------------------------------------------------------------------------
# load_config — missing required fields
# ---------------------------------------------------------------------------


def test_load_config_raises_when_providers_missing(tmp_path: Path) -> None:
    # No providers.yaml at all — providers is required
    with pytest.raises(ValidationError):
        load_config(tmp_path)


def test_load_config_raises_when_llm_primary_missing(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "providers.yaml",
        {"llm": {}, "embedding": {"primary": {"provider": "bedrock", "model": "m"}}},
    )
    with pytest.raises(ValidationError):
        load_config(tmp_path)


def test_load_config_raises_for_invalid_provider_name(tmp_path: Path) -> None:
    bad = {
        "llm": {"primary": {"provider": "unknown_provider", "model": "x"}},
        "embedding": {"primary": {"provider": "bedrock", "model": "y"}},
    }
    write_yaml(tmp_path / "providers.yaml", bad)
    with pytest.raises(ValidationError):
        load_config(tmp_path)


def test_load_config_raises_for_invalid_log_level(tmp_path: Path) -> None:
    write_yaml(tmp_path / "providers.yaml", MINIMAL_PROVIDERS)
    write_yaml(tmp_path / "app.yaml", {"logging": {"level": "VERBOSE"}})
    with pytest.raises(ValidationError):
        load_config(tmp_path)


# ---------------------------------------------------------------------------
# load_config — default values
# ---------------------------------------------------------------------------


def test_default_values_when_app_yaml_absent(tmp_path: Path) -> None:
    write_yaml(tmp_path / "providers.yaml", MINIMAL_PROVIDERS)
    config = load_config(tmp_path)
    assert config.app.server.host == "127.0.0.1"
    assert config.app.server.port == 8000
    assert config.app.logging.level == "INFO"
    assert config.app.chunking.size == 512
    assert config.app.chunking.overlap == 50
    assert config.app.retrieval.vector_weight == pytest.approx(0.6)
    assert config.app.retrieval.top_k == 10


def test_default_values_when_connectors_yaml_absent(tmp_path: Path) -> None:
    write_yaml(tmp_path / "providers.yaml", MINIMAL_PROVIDERS)
    config = load_config(tmp_path)
    assert config.connectors.teams.enabled is False
    assert config.connectors.obsidian.enabled is False
    assert config.connectors.jira.enabled is False


def test_llm_fallback_is_none_by_default(tmp_path: Path) -> None:
    write_yaml(tmp_path / "providers.yaml", MINIMAL_PROVIDERS)
    config = load_config(tmp_path)
    assert config.providers.llm.fallback is None
    assert config.providers.embedding.fallback is None


def test_default_llm_max_tokens_and_temperature(tmp_path: Path) -> None:
    write_yaml(tmp_path / "providers.yaml", MINIMAL_PROVIDERS)
    config = load_config(tmp_path)
    assert config.providers.llm.primary.max_tokens == 4096
    assert config.providers.llm.primary.temperature == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# load_config — environment variable overrides
# ---------------------------------------------------------------------------


def test_env_var_overrides_llm_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_yaml(tmp_path / "providers.yaml", MINIMAL_PROVIDERS)
    monkeypatch.setenv("NEXUSPKM_PROVIDERS__LLM__PRIMARY__PROVIDER", "openai")
    monkeypatch.setenv("NEXUSPKM_PROVIDERS__LLM__PRIMARY__MODEL", "gpt-4o")
    config = load_config(tmp_path)
    assert config.providers.llm.primary.provider == "openai"
    assert config.providers.llm.primary.model == "gpt-4o"


def test_env_var_overrides_app_server_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_yaml(tmp_path / "providers.yaml", MINIMAL_PROVIDERS)
    monkeypatch.setenv("NEXUSPKM_APP__SERVER__PORT", "9000")
    config = load_config(tmp_path)
    assert config.app.server.port == 9000


def test_env_var_overrides_connector_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_yaml(tmp_path / "providers.yaml", MINIMAL_PROVIDERS)
    write_yaml(tmp_path / "connectors.yaml", {"obsidian": {"enabled": False}})
    monkeypatch.setenv("NEXUSPKM_CONNECTORS__OBSIDIAN__ENABLED", "true")
    config = load_config(tmp_path)
    assert config.connectors.obsidian.enabled is True


def test_env_var_takes_precedence_over_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_yaml(tmp_path / "providers.yaml", FULL_PROVIDERS)
    monkeypatch.setenv("NEXUSPKM_PROVIDERS__LLM__PRIMARY__TEMPERATURE", "0.1")
    config = load_config(tmp_path)
    # YAML says 0.5, env var says 0.1 — env var wins
    assert config.providers.llm.primary.temperature == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# Secrets not in models
# ---------------------------------------------------------------------------


def test_no_api_key_fields_in_provider_config() -> None:
    """API keys must not be stored in config models — they come from env vars."""
    secret_names = {"api_key", "secret_key", "token", "password", "secret", "access_key"}
    for model_cls in (LLMProviderConfig, EmbeddingProviderConfig):
        found = set(model_cls.model_fields) & secret_names
        assert not found, f"Secret fields found in {model_cls.__name__}: {found}"


def test_no_api_key_fields_in_connector_configs() -> None:
    """Connector credentials must come from env vars, not config models."""
    secret_names = {"api_key", "secret_key", "token", "password", "secret", "client_secret"}
    for model_cls in (TeamsConnectorConfig, OutlookConnectorConfig, JiraConnectorConfig):
        found = set(model_cls.model_fields) & secret_names
        assert not found, f"Secret fields found in {model_cls.__name__}: {found}"
