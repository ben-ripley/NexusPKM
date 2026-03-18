"""YAML + environment variable configuration loader.

Loading priority (highest to lowest):
  1. Environment variables  (NEXUSPKM_ prefix, __ nested delimiter)
  2. YAML config files      (providers.yaml, app.yaml, connectors.yaml)
  3. Model defaults

Env var examples:
  NEXUSPKM_PROVIDERS__LLM__PRIMARY__PROVIDER=openai
  NEXUSPKM_PROVIDERS__LLM__PRIMARY__MODEL=gpt-4o
  NEXUSPKM_APP__SERVER__PORT=9000
  NEXUSPKM_CONNECTORS__OBSIDIAN__ENABLED=true
"""

import os
from pathlib import Path
from typing import Any

import yaml

from .models import NexusPKMConfig

_ENV_PREFIX = "NEXUSPKM_"
_ENV_DELIMITER = "__"


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, returning an empty dict if it does not exist."""
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into *base*, returning a new dict."""
    result: dict[str, Any] = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _set_nested(d: dict[str, Any], keys: list[str], value: str) -> None:
    """Set a value in a nested dict using a list of keys, creating missing levels."""
    for key in keys[:-1]:
        if key not in d or not isinstance(d[key], dict):
            d[key] = {}
        d = d[key]
    d[keys[-1]] = value


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """Apply NEXUSPKM_* environment variables onto the config dict.

    Variables use double-underscore as the nesting delimiter and are
    lowercased to match model field names.  Type coercion is left to
    Pydantic at validation time.
    """
    result = dict(config)
    prefix_len = len(_ENV_PREFIX)
    for name, value in os.environ.items():
        if not name.startswith(_ENV_PREFIX):
            continue
        # Strip prefix and split on double-underscore
        path = name[prefix_len:].lower().split(_ENV_DELIMITER.lower())
        _set_nested(result, path, value)
    return result


def load_config(config_dir: Path = Path("config")) -> NexusPKMConfig:
    """Load and validate the full application configuration.

    Args:
        config_dir: Directory containing providers.yaml, app.yaml, and
                    connectors.yaml.  Missing files are treated as empty
                    (defaults apply).  Raises ``ValidationError`` if the
                    resulting configuration is invalid.
    """
    providers_data = _load_yaml(config_dir / "providers.yaml")
    app_data = _load_yaml(config_dir / "app.yaml")
    connectors_data = _load_yaml(config_dir / "connectors.yaml")

    merged: dict[str, Any] = {
        "providers": providers_data,
        "app": app_data,
        "connectors": connectors_data,
    }

    merged = _apply_env_overrides(merged)

    return NexusPKMConfig.model_validate(merged)
