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

When overriding retrieval weights via env vars, all three must be set
together so that they continue to sum to 1.0:
  NEXUSPKM_APP__RETRIEVAL__VECTOR_WEIGHT=0.7
  NEXUSPKM_APP__RETRIEVAL__GRAPH_WEIGHT=0.2
  NEXUSPKM_APP__RETRIEVAL__RECENCY_WEIGHT=0.1

Note: ``load_config`` performs synchronous filesystem I/O and is intended
to be called exactly once at process startup, before the async event loop
begins (e.g., in a synchronous ``lifespan`` setup block).  Do not call it
from within an async request handler or coroutine.
"""

import asyncio
import copy
import os
from pathlib import Path
from typing import Any

import structlog
import yaml

from .models import NexusPKMConfig

log = structlog.get_logger()

_ENV_PREFIX = "NEXUSPKM_"
_ENV_DELIMITER = "__"

# Absolute path to the project-level config/ directory, derived from this file's location.
# This makes `load_config()` work correctly regardless of the process working directory.
# Layout: backend/src/nexuspkm/config/loader.py → parents[4] == project root
_DEFAULT_CONFIG_DIR = Path(__file__).parents[4] / "config"


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, returning an empty dict if it does not exist.

    Raises:
        ValueError: If the file exists but contains invalid YAML, or if its
                    top-level value is not a mapping (e.g., a bare scalar or list).
    """
    if not path.exists():
        log.debug("config_file_not_found_using_defaults", path=str(path))
        return {}
    with path.open() as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ValueError(f"Failed to parse {path.name}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(
            f"{path.name} must contain a YAML mapping at the top level, got {type(data).__name__}"
        )
    return data


def _set_nested(d: dict[str, Any], keys: list[str], value: str) -> None:
    """Set *value* at the nested path *keys* inside *d*, creating missing levels.

    If an intermediate key holds a non-dict value it is replaced with a dict.
    *value* is always a string — Pydantic coerces it to the target field type
    during model validation.
    """
    for key in keys[:-1]:
        if key not in d or not isinstance(d[key], dict):
            d[key] = {}
        d = d[key]
    d[keys[-1]] = value


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """Apply NEXUSPKM_* environment variables onto the config dict.

    Returns a deep copy of *config* with overrides applied so the original
    dicts (from YAML) are never mutated.  Variables use double-underscore as
    the nesting delimiter and are lowercased to match model field names.
    Type coercion is left to Pydantic at validation time.

    Env var names that produce empty path segments (e.g., ``NEXUSPKM_=value``,
    which would split to ``[""]``) are silently ignored.
    """
    result: dict[str, Any] = copy.deepcopy(config)
    for name, value in os.environ.items():
        if not name.startswith(_ENV_PREFIX):
            continue
        # Lowercased to match Pydantic field names — assumes all field names are lowercase.
        path = name.removeprefix(_ENV_PREFIX).lower().split(_ENV_DELIMITER)
        # Skip malformed names that produce empty segments
        if any(segment == "" for segment in path):
            continue
        _set_nested(result, path, value)
    return result


def load_config(config_dir: Path = _DEFAULT_CONFIG_DIR) -> NexusPKMConfig:
    """Load and validate the full application configuration.

    Args:
        config_dir: Directory containing providers.yaml, app.yaml, and
                    connectors.yaml.  Missing files are treated as empty
                    (defaults apply).  Defaults to the project-level config/
                    directory (absolute path derived from this file's location),
                    so the default is safe regardless of the process working
                    directory.  Pass an explicit path to override (e.g. in tests).

    Raises:
        RuntimeError: If called from within a running async event loop.
        ValueError: If a config file contains invalid YAML or a non-mapping
                    top-level value.
        ValidationError: If the resulting configuration fails Pydantic validation.
    """
    # Guard: synchronous I/O must not block a running event loop.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass  # No loop running — safe to proceed.
    else:
        raise RuntimeError(
            "load_config() must not be called from within a running event loop. "
            "Call it synchronously at application startup before the loop begins."
        )

    if not config_dir.exists():
        log.warning("config_dir_not_found_using_all_defaults", config_dir=str(config_dir))
    else:
        log.debug("loading_config", config_dir=str(config_dir))

    providers_data = _load_yaml(config_dir / "providers.yaml")
    app_data = _load_yaml(config_dir / "app.yaml")
    connectors_data = _load_yaml(config_dir / "connectors.yaml")

    merged: dict[str, Any] = {
        "providers": providers_data,
        "app": app_data,
        "connectors": connectors_data,
    }

    merged = _apply_env_overrides(merged)

    config = NexusPKMConfig.model_validate(merged)
    log.debug("config_loaded", llm_provider=config.providers.llm.primary.provider)
    return config
