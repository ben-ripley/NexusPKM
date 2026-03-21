"""Outlook Connector management API endpoints.

Exposes status, manual sync trigger, and configuration update for the
Outlook Connector.

Spec: F-010 API endpoints
NXP-69
"""

from __future__ import annotations

from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from nexuspkm.connectors.ms_graph.outlook import OutlookConnector
from nexuspkm.connectors.registry import ConnectorRegistry
from nexuspkm.connectors.scheduler import SyncScheduler

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/connectors/outlook", tags=["connectors"])


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class OutlookStatusResponse(BaseModel):
    name: str = "outlook"
    status: Literal["healthy", "degraded", "unavailable"]
    documents_synced: int = 0
    last_sync_at: str | None = None
    last_error: str | None = None
    folders: list[str] = Field(default_factory=list)
    calendar_window_days: int = 30


class OutlookConfigUpdate(BaseModel):
    sync_interval_minutes: int | None = Field(default=None, gt=0)
    folders: list[str] | None = None
    exclude_folders: list[str] | None = None
    sender_domains: list[str] | None = None
    max_emails_per_sync: int | None = Field(default=None, gt=0)
    calendar_window_days: int | None = Field(default=None, gt=0)


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
) -> OutlookStatusResponse:
    """Return the current Outlook connector status."""
    statuses = registry.get_all_statuses()
    status = statuses.get("outlook")
    if status is None:
        raise HTTPException(status_code=404, detail="Outlook connector not configured")

    connector = registry.get("outlook")
    folders: list[str] = []
    calendar_window_days = 30
    if isinstance(connector, OutlookConnector):
        folders = connector.config.folders
        calendar_window_days = connector.config.calendar_window_days

    last_sync_at_str: str | None = None
    if status.last_sync_at is not None:
        last_sync_at_str = status.last_sync_at.isoformat()

    return OutlookStatusResponse(
        status=status.status,
        documents_synced=status.documents_synced,
        last_sync_at=last_sync_at_str,
        last_error=status.last_error,
        folders=folders,
        calendar_window_days=calendar_window_days,
    )


@router.post("/sync")
async def trigger_sync(
    background_tasks: BackgroundTasks,
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    scheduler: Annotated[SyncScheduler, Depends(get_sync_scheduler)],
) -> SyncStartedResponse:
    """Trigger a manual sync for the Outlook connector."""
    if registry.get("outlook") is None:
        raise HTTPException(status_code=404, detail="Outlook connector not configured")

    background_tasks.add_task(scheduler.trigger_sync, "outlook")
    log.info("outlook_sync.manual_trigger")
    return SyncStartedResponse()


@router.put("/config")
async def update_config(
    payload: OutlookConfigUpdate,
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    scheduler: Annotated[SyncScheduler, Depends(get_sync_scheduler)],
) -> ConfigUpdatedResponse:
    """Update the Outlook connector configuration at runtime."""
    connector = registry.get("outlook")
    if not isinstance(connector, OutlookConnector):
        raise HTTPException(status_code=404, detail="Outlook connector not configured")

    updates: dict[str, object] = {}
    if payload.folders is not None:
        updates["folders"] = payload.folders
    if payload.exclude_folders is not None:
        updates["exclude_folders"] = payload.exclude_folders
    if payload.sender_domains is not None:
        updates["sender_domains"] = payload.sender_domains
    if payload.max_emails_per_sync is not None:
        updates["max_emails_per_sync"] = payload.max_emails_per_sync
    if payload.calendar_window_days is not None:
        updates["calendar_window_days"] = payload.calendar_window_days

    new_interval = (
        payload.sync_interval_minutes
        if payload.sync_interval_minutes is not None
        else connector.config.sync_interval_minutes
    )

    if payload.sync_interval_minutes is not None:
        previous_config = connector.config  # snapshot full config before any changes
        updates["sync_interval_minutes"] = new_interval
        connector.update_config(**updates)
        try:
            scheduler.reschedule_connector("outlook", new_interval * 60)
        except Exception as exc:
            # Restore entire previous config (not just the interval)
            connector.update_config(**previous_config.model_dump())
            log.error("outlook_config_update_failed", error=str(exc), exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to reschedule connector") from exc
    elif updates:
        connector.update_config(**updates)

    log.info("outlook_config_updated", sync_interval_minutes=new_interval)
    return ConfigUpdatedResponse(sync_interval_minutes=new_interval)
