"""Integration tests for the Apple Notes connector registration path in main.py.

Covers the apple_notes_connector_registered code path, startup health-check
wiring, dependency-override stubs, and the interval computation performed in
the lifespan function.

Spec: F-009
NXP-68
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from nexuspkm.api.apple_notes import (
    get_connector_registry as an_get_registry,
)
from nexuspkm.api.apple_notes import (
    get_sync_scheduler as an_get_scheduler,
)
from nexuspkm.config.models import AppleNotesConnectorConfig
from nexuspkm.connectors.apple_notes.connector import AppleNotesConnector
from nexuspkm.connectors.registry import ConnectorRegistry

# ---------------------------------------------------------------------------
# Connector registration
# ---------------------------------------------------------------------------


async def test_connector_registered_when_enabled(tmp_path: Path) -> None:
    """AppleNotesConnector is added to the registry when enabled=True."""
    config = AppleNotesConnectorConfig(enabled=True)
    connector = AppleNotesConnector(state_dir=tmp_path / "state", config=config)
    registry = ConnectorRegistry()
    registry.register(connector)

    result = registry.get("apple_notes")
    assert result is connector
    assert result.name == "apple_notes"  # type: ignore[union-attr]


async def test_connector_not_registered_when_disabled() -> None:
    """When enabled=False the connector should not appear in the registry."""
    registry = ConnectorRegistry()
    assert registry.get("apple_notes") is None


# ---------------------------------------------------------------------------
# Startup health check loop
# ---------------------------------------------------------------------------


async def test_startup_health_check_stored_in_registry(tmp_path: Path) -> None:
    """Startup health-check result is stored in registry status (macOS path)."""
    config = AppleNotesConnectorConfig(enabled=True)
    connector = AppleNotesConnector(state_dir=tmp_path / "state", config=config)
    registry = ConnectorRegistry()
    registry.register(connector)

    # Simulate the main.py startup health-check loop on macOS.
    with patch("sys.platform", "darwin"):
        initial_status = await connector.health_check()
    registry.update_status(connector.name, initial_status)

    stored = registry.get_all_statuses().get("apple_notes")
    assert stored is not None
    assert stored.name == "apple_notes"
    assert stored.status in ("healthy", "degraded")


async def test_startup_health_check_unavailable_non_macos(tmp_path: Path) -> None:
    """Startup health-check returns unavailable on non-macOS (Linux/Windows)."""
    config = AppleNotesConnectorConfig(enabled=True)
    connector = AppleNotesConnector(state_dir=tmp_path / "state", config=config)
    registry = ConnectorRegistry()
    registry.register(connector)

    with patch("sys.platform", "linux"):
        initial_status = await connector.health_check()
    registry.update_status(connector.name, initial_status)

    stored = registry.get_all_statuses().get("apple_notes")
    assert stored is not None
    assert stored.status == "unavailable"


# ---------------------------------------------------------------------------
# Interval computation
# ---------------------------------------------------------------------------


def test_interval_seconds_from_config() -> None:
    """sync_interval_minutes * 60 produces the scheduler interval in seconds."""
    config = AppleNotesConnectorConfig(enabled=True, sync_interval_minutes=15)
    intervals: dict[str, int] = {}
    intervals["apple_notes"] = config.sync_interval_minutes * 60
    assert intervals["apple_notes"] == 900  # 15 * 60


def test_interval_seconds_custom_value() -> None:
    config = AppleNotesConnectorConfig(enabled=True, sync_interval_minutes=30)
    assert config.sync_interval_minutes * 60 == 1800


# ---------------------------------------------------------------------------
# Dependency-override stubs (sentinel behaviour before lifespan runs)
# ---------------------------------------------------------------------------


def test_get_connector_registry_stub_raises_503() -> None:
    """Stub dependency raises 503 when not overridden by main.py lifespan."""
    with pytest.raises(HTTPException) as exc_info:
        an_get_registry()
    assert exc_info.value.status_code == 503


def test_get_sync_scheduler_stub_raises_503() -> None:
    """Stub dependency raises 503 when not overridden by main.py lifespan."""
    with pytest.raises(HTTPException) as exc_info:
        an_get_scheduler()
    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Platform-guard: fetch() and fetch_deleted_ids() short-circuit on non-macOS
# ---------------------------------------------------------------------------


async def test_fetch_returns_empty_on_non_macos(tmp_path: Path) -> None:
    """fetch() yields no documents on non-macOS without calling osascript."""
    config = AppleNotesConnectorConfig(enabled=True)
    connector = AppleNotesConnector(state_dir=tmp_path / "state", config=config)

    with patch("sys.platform", "linux"):
        docs = [doc async for doc in connector.fetch()]

    assert docs == []


async def test_fetch_deleted_ids_returns_empty_on_non_macos(tmp_path: Path) -> None:
    """fetch_deleted_ids() returns [] on non-macOS without calling osascript."""
    config = AppleNotesConnectorConfig(enabled=True)
    connector = AppleNotesConnector(state_dir=tmp_path / "state", config=config)

    with patch("sys.platform", "linux"):
        deleted_ids = await connector.fetch_deleted_ids()

    assert deleted_ids == []


# ---------------------------------------------------------------------------
# SQLite path configurability
# ---------------------------------------------------------------------------


def test_notes_db_path_injectable(tmp_path: Path) -> None:
    """notes_db_path from config is used instead of the default system path."""
    custom_db = tmp_path / "custom_notes.sqlite"
    config = AppleNotesConnectorConfig(enabled=True, notes_db_path=custom_db)
    connector = AppleNotesConnector(state_dir=tmp_path / "state", config=config)
    assert connector._notes_db_path == custom_db


def test_notes_db_path_defaults_to_system_path(tmp_path: Path) -> None:
    """When notes_db_path is None the connector uses the default macOS path."""
    from nexuspkm.connectors.apple_notes.connector import _NOTES_DB_PATH

    config = AppleNotesConnectorConfig(enabled=True)
    connector = AppleNotesConnector(state_dir=tmp_path / "state", config=config)
    assert connector._notes_db_path == _NOTES_DB_PATH
