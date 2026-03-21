"""Apple Notes Connector management API endpoints.

Exposes status, manual sync trigger, and configuration update for the
Apple Notes Connector.

Spec: F-009 API endpoints
NXP-68
"""

from __future__ import annotations

import sys
from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from nexuspkm.connectors.apple_notes.connector import AppleNotesConnector
from nexuspkm.connectors.registry import ConnectorRegistry
from nexuspkm.connectors.scheduler import SyncScheduler

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/connectors/apple-notes", tags=["connectors"])


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class AppleNotesStatusResponse(BaseModel):
    name: str = "apple_notes"
    status: Literal["healthy", "degraded", "unavailable"]
    documents_synced: int = 0
    extraction_method: str = "applescript"
    platform_supported: bool


class AppleNotesConfigUpdate(BaseModel):
    sync_interval_minutes: int = Field(default=15, gt=0, le=1440)


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
) -> AppleNotesStatusResponse:
    """Return the current Apple Notes connector status."""
    statuses = registry.get_all_statuses()
    status = statuses.get("apple_notes")
    if status is None:
        raise HTTPException(status_code=404, detail="Apple Notes connector not configured")

    connector = registry.get("apple_notes")
    extraction_method = "applescript"
    if isinstance(connector, AppleNotesConnector):
        extraction_method = connector.extraction_method

    return AppleNotesStatusResponse(
        status=status.status,
        documents_synced=status.documents_synced,
        extraction_method=extraction_method,
        platform_supported=sys.platform == "darwin",
    )


@router.post("/sync")
async def trigger_sync(
    background_tasks: BackgroundTasks,
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    scheduler: Annotated[SyncScheduler, Depends(get_sync_scheduler)],
) -> SyncStartedResponse:
    """Trigger a manual sync for the Apple Notes connector."""
    if registry.get("apple_notes") is None:
        raise HTTPException(status_code=404, detail="Apple Notes connector not configured")

    background_tasks.add_task(scheduler.trigger_sync, "apple_notes")
    log.info("apple_notes_sync.manual_trigger")
    return SyncStartedResponse()


@router.put("/config")
async def update_config(
    payload: AppleNotesConfigUpdate,
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    scheduler: Annotated[SyncScheduler, Depends(get_sync_scheduler)],
) -> ConfigUpdatedResponse:
    """Update the Apple Notes connector configuration at runtime."""
    connector = registry.get("apple_notes")
    if not isinstance(connector, AppleNotesConnector):
        raise HTTPException(status_code=404, detail="Apple Notes connector not configured")

    connector.update_sync_interval(payload.sync_interval_minutes)
    scheduler.reschedule_connector("apple_notes", payload.sync_interval_minutes * 60)
    log.info(
        "apple_notes_config_updated",
        sync_interval_minutes=payload.sync_interval_minutes,
    )
    return ConfigUpdatedResponse(sync_interval_minutes=payload.sync_interval_minutes)
