"""JIRA Connector management API endpoints.

Exposes status, manual sync trigger, and configuration update for the
JIRA Connector.

Spec: F-011 API endpoints
NXP-85
"""

from __future__ import annotations

from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from nexuspkm.connectors.jira.connector import JiraConnector
from nexuspkm.connectors.registry import ConnectorRegistry
from nexuspkm.connectors.scheduler import SyncScheduler

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/connectors/jira", tags=["connectors"])


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class JiraStatusResponse(BaseModel):
    name: str = "jira"
    status: Literal["healthy", "degraded", "unavailable"]
    documents_synced: int = 0
    base_url: str
    jql_filter: str


class JiraConfigUpdate(BaseModel):
    sync_interval_minutes: int = Field(default=30, gt=0, le=1440)


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
) -> JiraStatusResponse:
    """Return the current JIRA connector status."""
    statuses = registry.get_all_statuses()
    status = statuses.get("jira")
    if status is None:
        raise HTTPException(status_code=404, detail="JIRA connector not configured")

    connector = registry.get("jira")
    base_url = ""
    jql_filter = ""
    if isinstance(connector, JiraConnector):
        base_url = connector.base_url
        jql_filter = connector.jql_filter

    return JiraStatusResponse(
        status=status.status,
        documents_synced=status.documents_synced,
        base_url=base_url,
        jql_filter=jql_filter,
    )


@router.post("/sync")
async def trigger_sync(
    background_tasks: BackgroundTasks,
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    scheduler: Annotated[SyncScheduler, Depends(get_sync_scheduler)],
) -> SyncStartedResponse:
    """Trigger a manual sync for the JIRA connector."""
    if registry.get("jira") is None:
        raise HTTPException(status_code=404, detail="JIRA connector not configured")

    background_tasks.add_task(scheduler.trigger_sync, "jira")
    log.info("jira_sync.manual_trigger")
    return SyncStartedResponse()


@router.put("/config")
async def update_config(
    payload: JiraConfigUpdate,
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    scheduler: Annotated[SyncScheduler, Depends(get_sync_scheduler)],
) -> ConfigUpdatedResponse:
    """Update the JIRA connector configuration at runtime."""
    connector = registry.get("jira")
    if not isinstance(connector, JiraConnector):
        raise HTTPException(status_code=404, detail="JIRA connector not configured")

    previous_interval = connector.sync_interval_minutes
    connector.update_sync_interval(payload.sync_interval_minutes)
    try:
        scheduler.reschedule_connector("jira", payload.sync_interval_minutes * 60)
    except Exception as exc:
        connector.update_sync_interval(previous_interval)
        log.error("jira_config_update_failed", error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to reschedule connector") from exc
    log.info("jira_config_updated", sync_interval_minutes=payload.sync_interval_minutes)
    return ConfigUpdatedResponse(sync_interval_minutes=payload.sync_interval_minutes)
