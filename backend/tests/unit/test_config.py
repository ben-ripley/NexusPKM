"""Tests for the configuration loading system (NXP-29)."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from nexuspkm.config import load_config
from nexuspkm.config.loader import _apply_env_overrides, _load_yaml, _set_nested
from nexuspkm.config.models import (
    EmbeddingProviderConfig,
    JiraConnectorConfig,
    LLMProviderConfig,
    NexusPKMConfig,
    ObsidianConnectorConfig,
    OutlookConnectorConfig,
    RetrievalConfig,
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


def write_yaml(path: Path, data: dict[str, Any]) -> None:
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
    assert config.connectors.obsidian.vault_path == Path("~/Notes").expanduser()
    assert config.connectors.teams.enabled is False


def test_load_config_raises_on_non_mapping_yaml(tmp_path: Path) -> None:
    (tmp_path / "providers.yaml").write_text("- just a list\n")
    with pytest.raises(ValueError, match="providers.yaml"):
        load_config(tmp_path)


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
    write_yaml(tmp_path / "connectors.yaml", {"teams": {"enabled": False}})
    monkeypatch.setenv("NEXUSPKM_CONNECTORS__TEAMS__ENABLED", "true")
    config = load_config(tmp_path)
    assert config.connectors.teams.enabled is True


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


# ---------------------------------------------------------------------------
# _set_nested
# ---------------------------------------------------------------------------


def test_set_nested_single_key() -> None:
    d: dict[str, object] = {}
    _set_nested(d, ["port"], "9000")
    assert d == {"port": "9000"}


def test_set_nested_two_levels() -> None:
    d: dict[str, object] = {}
    _set_nested(d, ["server", "port"], "9000")
    assert d == {"server": {"port": "9000"}}


def test_set_nested_three_levels() -> None:
    d: dict[str, object] = {}
    _set_nested(d, ["providers", "llm", "primary"], "bedrock")
    assert d == {"providers": {"llm": {"primary": "bedrock"}}}


def test_set_nested_merges_existing_dict() -> None:
    d: dict[str, object] = {"server": {"host": "127.0.0.1"}}
    _set_nested(d, ["server", "port"], "9000")
    assert d == {"server": {"host": "127.0.0.1", "port": "9000"}}


def test_set_nested_overwrites_scalar_with_dict() -> None:
    """When an intermediate key holds a scalar, it is replaced with a dict."""
    d: dict[str, object] = {"server": "old_value"}
    _set_nested(d, ["server", "port"], "9000")
    assert d == {"server": {"port": "9000"}}


# ---------------------------------------------------------------------------
# yaml.YAMLError handling
# ---------------------------------------------------------------------------


def test_load_config_raises_on_malformed_yaml(tmp_path: Path) -> None:
    (tmp_path / "providers.yaml").write_text("llm: [unclosed bracket")
    with pytest.raises(ValueError, match="providers.yaml"):
        load_config(tmp_path)


def test_load_config_raises_on_malformed_app_yaml(tmp_path: Path) -> None:
    write_yaml(tmp_path / "providers.yaml", MINIMAL_PROVIDERS)
    (tmp_path / "app.yaml").write_text(": invalid: yaml: {{")
    with pytest.raises(ValueError, match="app.yaml"):
        load_config(tmp_path)


# ---------------------------------------------------------------------------
# Model validators
# ---------------------------------------------------------------------------


def test_jira_connector_base_url_none_by_default() -> None:
    config = JiraConnectorConfig()
    assert config.base_url is None


def test_jira_connector_raises_when_enabled_without_base_url() -> None:
    with pytest.raises(ValidationError):
        JiraConnectorConfig(enabled=True)


def test_jira_connector_valid_when_enabled_with_base_url() -> None:
    config = JiraConnectorConfig(enabled=True, base_url="https://myorg.atlassian.net")
    assert config.enabled is True


def test_retrieval_weights_sum_to_one() -> None:
    config = RetrievalConfig()
    total = config.vector_weight + config.graph_weight + config.recency_weight
    assert total == pytest.approx(1.0)


def test_retrieval_weights_validation_error_when_sum_not_one() -> None:
    with pytest.raises(ValidationError):
        RetrievalConfig(vector_weight=0.5, graph_weight=0.5, recency_weight=0.5)


# ---------------------------------------------------------------------------
# ObsidianConnectorConfig validators
# ---------------------------------------------------------------------------


def test_obsidian_vault_path_none_by_default() -> None:
    config = ObsidianConnectorConfig()
    assert config.vault_path is None


def test_obsidian_raises_when_enabled_without_vault_path() -> None:
    with pytest.raises(ValidationError):
        ObsidianConnectorConfig(enabled=True)


def test_obsidian_valid_when_enabled_with_vault_path() -> None:
    config = ObsidianConnectorConfig(enabled=True, vault_path="~/Documents/Notes")
    assert config.vault_path == Path("~/Documents/Notes").expanduser()


def test_obsidian_vault_path_is_expanded() -> None:
    config = ObsidianConnectorConfig(vault_path="~/Notes")
    assert config.vault_path == Path("~/Notes").expanduser()
    assert config.vault_path is not None
    assert not str(config.vault_path).startswith("~")


# ---------------------------------------------------------------------------
# _apply_env_overrides
# ---------------------------------------------------------------------------


def test_apply_env_overrides_sets_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUSPKM_PROVIDERS__LLM__PRIMARY__PROVIDER", "openai")
    result = _apply_env_overrides({})
    assert result["providers"]["llm"]["primary"]["provider"] == "openai"


def test_apply_env_overrides_does_not_mutate_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUSPKM_PROVIDERS__LLM__PRIMARY__PROVIDER", "openai")
    original: dict[str, Any] = {"providers": {"llm": {"primary": {"provider": "bedrock"}}}}
    _apply_env_overrides(original)
    # original must be unchanged (deep copy)
    assert original["providers"]["llm"]["primary"]["provider"] == "bedrock"


def test_apply_env_overrides_ignores_empty_segment(monkeypatch: pytest.MonkeyPatch) -> None:
    # NEXUSPKM_=value produces path [""] — must be silently ignored
    monkeypatch.setenv("NEXUSPKM_", "value")
    result = _apply_env_overrides({})
    assert "" not in result


def test_apply_env_overrides_ignores_double_delimiter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # NEXUSPKM_APP____PORT produces path ["app", "", "port"] — ignored
    monkeypatch.setenv("NEXUSPKM_APP____PORT", "9000")
    result = _apply_env_overrides({})
    assert result.get("app") is None


# ---------------------------------------------------------------------------
# load_config — env-var-only startup (no config directory)
# ---------------------------------------------------------------------------


def test_load_config_succeeds_without_config_dir_when_env_vars_supply_required_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Config dir may not exist in containerised deployments — env vars are sufficient."""
    nonexistent = tmp_path / "does_not_exist"
    monkeypatch.setenv("NEXUSPKM_PROVIDERS__LLM__PRIMARY__PROVIDER", "openai")
    monkeypatch.setenv("NEXUSPKM_PROVIDERS__LLM__PRIMARY__MODEL", "gpt-4o")
    monkeypatch.setenv("NEXUSPKM_PROVIDERS__EMBEDDING__PRIMARY__PROVIDER", "openai")
    monkeypatch.setenv("NEXUSPKM_PROVIDERS__EMBEDDING__PRIMARY__MODEL", "text-embedding-3-small")
    config = load_config(nonexistent)
    assert config.providers.llm.primary.provider == "openai"
    assert config.providers.llm.primary.model == "gpt-4o"


def test_load_config_raises_when_obsidian_enabled_via_env_without_vault_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Enabling Obsidian via env var without vault_path must fail validation."""
    write_yaml(tmp_path / "providers.yaml", MINIMAL_PROVIDERS)
    monkeypatch.setenv("NEXUSPKM_CONNECTORS__OBSIDIAN__ENABLED", "true")
    with pytest.raises(ValidationError):
        load_config(tmp_path)


# ---------------------------------------------------------------------------
# _load_yaml
# ---------------------------------------------------------------------------


def test_load_yaml_returns_empty_dict_for_missing_file(tmp_path: Path) -> None:
    assert _load_yaml(tmp_path / "nonexistent.yaml") == {}


def test_load_yaml_returns_empty_dict_for_empty_file(tmp_path: Path) -> None:
    (tmp_path / "empty.yaml").write_text("")
    assert _load_yaml(tmp_path / "empty.yaml") == {}


def test_load_yaml_raises_on_malformed_yaml(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text("key: [unclosed")
    with pytest.raises(ValueError, match="bad.yaml"):
        _load_yaml(tmp_path / "bad.yaml")


def test_load_yaml_raises_on_non_mapping_top_level(tmp_path: Path) -> None:
    (tmp_path / "list.yaml").write_text("- item1\n- item2\n")
    with pytest.raises(ValueError, match="list.yaml"):
        _load_yaml(tmp_path / "list.yaml")
