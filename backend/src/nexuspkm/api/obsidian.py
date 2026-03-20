"""Obsidian Connector management API endpoints.

Exposes status, manual sync trigger, and configuration update for the
Obsidian Notes Connector.

Spec: F-004 API endpoints
NXP-49
"""

from __future__ import annotations

from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from nexuspkm.connectors.obsidian.connector import ObsidianNotesConnector
from nexuspkm.connectors.registry import ConnectorRegistry
from nexuspkm.connectors.scheduler import SyncScheduler

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/connectors/obsidian", tags=["connectors"])


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class ObsidianStatusResponse(BaseModel):
    name: str = "obsidian"
    status: Literal["healthy", "degraded", "unavailable"]
    vault_path: str | None = None
    documents_synced: int = 0
    watcher_running: bool = False


class ObsidianConfigUpdate(BaseModel):
    sync_interval_minutes: int = Field(default=5, gt=0, le=1440)


class SyncStartedResponse(BaseModel):
    status: Literal["sync_started"] = "sync_started"


class ConfigUpdatedResponse(BaseModel):
    status: Literal["updated"] = "updated"
    sync_interval_minutes: int


# ---------------------------------------------------------------------------
# Dependency providers (overridden in main.py lifespan)
# ---------------------------------------------------------------------------


def get_connector_registry() -> ConnectorRegistry:
    """Dependency: returns the active ConnectorRegistry."""
    raise HTTPException(  # pragma: no cover
        status_code=503, detail="Connector registry not initialised"
    )


def get_sync_scheduler() -> SyncScheduler:
    """Dependency: returns the active SyncScheduler."""
    raise HTTPException(  # pragma: no cover
        status_code=503, detail="Sync scheduler not initialised"
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status")
async def get_status(
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
) -> ObsidianStatusResponse:
    """Return the current Obsidian connector status."""
    statuses = registry.get_all_statuses()
    status = statuses.get("obsidian")
    if status is None:
        raise HTTPException(status_code=404, detail="Obsidian connector not configured")

    connector = registry.get("obsidian")
    vault_path: str | None = None
    watcher_running = False
    if isinstance(connector, ObsidianNotesConnector):
        vault_path = str(connector.vault_path)
        watcher_running = connector.watcher_running

    return ObsidianStatusResponse(
        status=status.status,
        vault_path=vault_path,
        documents_synced=status.documents_synced,
        watcher_running=watcher_running,
    )


@router.post("/sync")
async def trigger_sync(
    background_tasks: BackgroundTasks,
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    scheduler: Annotated[SyncScheduler, Depends(get_sync_scheduler)],
) -> SyncStartedResponse:
    """Trigger a manual sync for the Obsidian connector."""
    if registry.get("obsidian") is None:
        raise HTTPException(status_code=404, detail="Obsidian connector not configured")

    background_tasks.add_task(scheduler.trigger_sync, "obsidian")
    log.info("obsidian_sync.manual_trigger")
    return SyncStartedResponse()


@router.put("/config")
async def update_config(
    payload: ObsidianConfigUpdate,
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    scheduler: Annotated[SyncScheduler, Depends(get_sync_scheduler)],
) -> ConfigUpdatedResponse:
    """Update the Obsidian connector configuration at runtime."""
    connector = registry.get("obsidian")
    if not isinstance(connector, ObsidianNotesConnector):
        raise HTTPException(status_code=404, detail="Obsidian connector not configured")

    connector.update_sync_interval(payload.sync_interval_minutes)
    scheduler.reschedule_connector("obsidian", payload.sync_interval_minutes * 60)
    log.info(
        "obsidian_config_updated",
        sync_interval_minutes=payload.sync_interval_minutes,
    )
    return ConfigUpdatedResponse(sync_interval_minutes=payload.sync_interval_minutes)
