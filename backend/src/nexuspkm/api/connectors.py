"""Teams Connector management API endpoints.

Exposes device code auth flow initiation, sync status, manual sync trigger,
and configuration update for the Teams Transcript Connector.

Spec: F-003 API endpoints
NXP-56
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import AwareDatetime, BaseModel, Field

from nexuspkm.connectors.registry import ConnectorRegistry
from nexuspkm.connectors.scheduler import SyncScheduler

log = structlog.get_logger()

router = APIRouter(prefix="/api/connectors/teams", tags=["connectors"])


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class TeamsStatusResponse(BaseModel):
    name: str = "teams"
    status: Literal["healthy", "degraded", "unavailable"]
    last_sync_at: AwareDatetime | None = None
    last_error: str | None = None
    documents_synced: int = 0


class TeamsAuthResponse(BaseModel):
    user_code: str
    verification_uri: str
    expires_in: int
    message: str


class TeamsConfigUpdate(BaseModel):
    sync_interval_minutes: int = Field(default=30, gt=0)


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


@router.post("/authenticate")
async def authenticate(
    background_tasks: BackgroundTasks,
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
) -> TeamsAuthResponse:
    """Initiate the Microsoft Graph Device Code auth flow.

    Returns the user_code and verification_uri to display to the user.
    Starts a background task to poll for the token once the user authenticates.
    """
    from nexuspkm.connectors.ms_graph.teams import TeamsTranscriptConnector

    connector = registry.get("teams")
    if not isinstance(connector, TeamsTranscriptConnector):
        raise HTTPException(status_code=404, detail="Teams connector not configured")

    try:
        info, context = await connector._auth.initiate_device_code_flow()
    except (RuntimeError, ValueError) as exc:
        log.error("teams_auth.initiate_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    background_tasks.add_task(connector._auth.poll_for_token, context)

    log.info("teams_auth.device_flow_initiated", verification_uri=info.verification_uri)
    return TeamsAuthResponse(
        user_code=info.user_code,
        verification_uri=info.verification_uri,
        expires_in=info.expires_in,
        message=info.message,
    )


@router.get("/status")
async def get_status(
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
) -> TeamsStatusResponse:
    """Return the current Teams connector status."""
    statuses = registry.get_all_statuses()
    status = statuses.get("teams")
    if status is None:
        raise HTTPException(status_code=404, detail="Teams connector not configured")
    return TeamsStatusResponse(
        status=status.status,
        last_sync_at=status.last_sync_at,
        last_error=status.last_error,
        documents_synced=status.documents_synced,
    )


@router.post("/sync")
async def trigger_sync(
    background_tasks: BackgroundTasks,
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    scheduler: Annotated[SyncScheduler, Depends(get_sync_scheduler)],
) -> dict[str, Any]:
    """Trigger a manual sync for the Teams connector."""
    if registry.get("teams") is None:
        raise HTTPException(status_code=404, detail="Teams connector not configured")

    background_tasks.add_task(scheduler._sync_connector, "teams")
    log.info("teams_sync.manual_trigger")
    return {"status": "sync_started"}


@router.put("/config")
async def update_config(
    payload: TeamsConfigUpdate,
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
) -> dict[str, Any]:
    """Update the Teams connector configuration at runtime."""
    from nexuspkm.config.models import TeamsConnectorConfig
    from nexuspkm.connectors.ms_graph.teams import TeamsTranscriptConnector

    connector = registry.get("teams")
    if not isinstance(connector, TeamsTranscriptConnector):
        raise HTTPException(status_code=404, detail="Teams connector not configured")

    connector._config = TeamsConnectorConfig(
        enabled=connector._config.enabled,
        sync_interval_minutes=payload.sync_interval_minutes,
    )
    log.info(
        "teams_config_updated",
        sync_interval_minutes=payload.sync_interval_minutes,
    )
    return {"status": "updated", "sync_interval_minutes": payload.sync_interval_minutes}
