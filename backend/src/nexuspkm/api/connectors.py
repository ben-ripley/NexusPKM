"""Connector management API endpoints.

Exposes:
  - Teams-specific: device code auth flow, sync status, manual sync, config update.
  - Generic (connector-agnostic): list all statuses, trigger sync, update config,
    and initiate MS device-code auth for any MS-capable connector.

Spec: F-003 API endpoints
NXP-56, NXP-50
"""

from __future__ import annotations

from typing import Annotated, Literal, Protocol, runtime_checkable

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path
from pydantic import AwareDatetime, BaseModel, Field

from nexuspkm.config.models import TeamsConnectorConfig
from nexuspkm.connectors.ms_graph.auth import AuthFlowContext, DeviceCodeInfo
from nexuspkm.connectors.ms_graph.teams import TeamsTranscriptConnector
from nexuspkm.connectors.registry import ConnectorRegistry
from nexuspkm.connectors.scheduler import SyncScheduler

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/connectors/teams", tags=["connectors"])
generic_router = APIRouter(prefix="/api/connectors", tags=["connectors"])

# Connector names are validated against this pattern to prevent path traversal
# and excessively long inputs. "status" is reserved by the generic GET /status
# endpoint and must not be used as a connector name.
_CONNECTOR_NAME_PATTERN = r"^[a-zA-Z0-9_\-]{1,64}$"


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class MSAuthConnector(Protocol):
    """Duck-typing protocol for connectors that support MS device-code auth.

    NOTE: runtime_checkable Protocol checks via isinstance() only verify that
    the named attributes *exist* — not that they are async or have the correct
    signature. MagicMock(spec=TeamsTranscriptConnector) passes this check
    because the spec exposes all attributes of TeamsTranscriptConnector.
    This is intentional: any connector class that declares these methods is
    treated as MS-auth capable.
    """

    async def initiate_auth_flow(self) -> tuple[DeviceCodeInfo, AuthFlowContext]: ...

    async def complete_auth_flow(self, context: AuthFlowContext) -> bool: ...


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
    sync_interval_minutes: int = Field(default=30, gt=0, le=1440)


class SyncStartedResponse(BaseModel):
    status: Literal["sync_started"] = "sync_started"


class ConfigUpdatedResponse(BaseModel):
    status: Literal["updated"] = "updated"
    sync_interval_minutes: int


class ConnectorStatusItem(BaseModel):
    """Runtime health and sync statistics for a single connector."""

    name: str
    status: Literal["healthy", "degraded", "unavailable"]
    last_sync_at: AwareDatetime | None = None
    last_error: str | None = None
    documents_synced: int = 0


class GenericConfigUpdate(BaseModel):
    """Request body for updating a connector's sync interval."""

    sync_interval_minutes: int = Field(default=30, gt=0, le=1440)


class MSDeviceCodeResponse(BaseModel):
    """Response for any MS device-code auth initiation (connector-agnostic)."""

    user_code: str
    verification_uri: str
    expires_in: int
    message: str


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
# Teams-specific background helpers
# ---------------------------------------------------------------------------


async def _poll_for_token_with_logging(
    connector: TeamsTranscriptConnector, context: AuthFlowContext
) -> None:
    """Background wrapper that logs errors from the device code poll."""
    try:
        success = await connector.complete_auth_flow(context)
        if not success:
            log.warning("teams_auth.device_flow_failed")
    except Exception as exc:
        log.error("teams_auth.poll_error", error=str(exc), exc_info=True)


# ---------------------------------------------------------------------------
# Generic background helper
# ---------------------------------------------------------------------------


async def _poll_for_ms_token(
    connector: MSAuthConnector, context: AuthFlowContext, connector_name: str
) -> None:
    """Background task: polls for MS device-code token and logs outcome."""
    try:
        success = await connector.complete_auth_flow(context)
        if not success:
            log.warning("ms_auth.device_flow_failed", connector=connector_name)
    except Exception as exc:
        log.error("ms_auth.poll_error", connector=connector_name, error=str(exc), exc_info=True)


# ---------------------------------------------------------------------------
# Teams-specific endpoints
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
    connector = registry.get("teams")
    if not isinstance(connector, TeamsTranscriptConnector):
        raise HTTPException(status_code=404, detail="Teams connector not configured")

    try:
        info, context = await connector.initiate_auth_flow()
    except (RuntimeError, ValueError) as exc:
        log.error("teams_auth.initiate_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    background_tasks.add_task(_poll_for_token_with_logging, connector, context)

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
) -> SyncStartedResponse:
    """Trigger a manual sync for the Teams connector."""
    if registry.get("teams") is None:
        raise HTTPException(status_code=404, detail="Teams connector not configured")

    background_tasks.add_task(scheduler.trigger_sync, "teams")
    log.info("teams_sync.manual_trigger")
    return SyncStartedResponse()


@router.put("/config")
async def update_config(
    payload: TeamsConfigUpdate,
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    scheduler: Annotated[SyncScheduler, Depends(get_sync_scheduler)],
) -> ConfigUpdatedResponse:
    """Update the Teams connector configuration at runtime."""
    connector = registry.get("teams")
    if not isinstance(connector, TeamsTranscriptConnector):
        raise HTTPException(status_code=404, detail="Teams connector not configured")

    connector._config = TeamsConnectorConfig(
        enabled=connector._config.enabled,
        sync_interval_minutes=payload.sync_interval_minutes,
    )
    scheduler.reschedule_connector("teams", payload.sync_interval_minutes * 60)
    log.info(
        "teams_config_updated",
        sync_interval_minutes=payload.sync_interval_minutes,
    )
    return ConfigUpdatedResponse(sync_interval_minutes=payload.sync_interval_minutes)


# ---------------------------------------------------------------------------
# Generic connector endpoints
# ---------------------------------------------------------------------------


@generic_router.get("/status")
async def list_connector_statuses(
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
) -> list[ConnectorStatusItem]:
    """Return status for all registered connectors."""
    statuses = registry.get_all_statuses()
    return [
        ConnectorStatusItem(
            name=name,
            status=s.status,
            last_sync_at=s.last_sync_at,
            last_error=s.last_error,
            documents_synced=s.documents_synced,
        )
        for name, s in statuses.items()
    ]


@generic_router.post("/{name}/sync")
async def generic_trigger_sync(
    name: Annotated[str, Path(pattern=_CONNECTOR_NAME_PATTERN)],
    background_tasks: BackgroundTasks,
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    scheduler: Annotated[SyncScheduler, Depends(get_sync_scheduler)],
) -> SyncStartedResponse:
    """Trigger a manual sync for any registered connector."""
    if registry.get(name) is None:
        raise HTTPException(status_code=404, detail=f"Connector '{name}' not registered")

    background_tasks.add_task(scheduler.trigger_sync, name)
    log.info("connector_sync.manual_trigger", connector=name)
    return SyncStartedResponse()


@generic_router.put("/{name}/config")
async def generic_update_config(
    name: Annotated[str, Path(pattern=_CONNECTOR_NAME_PATTERN)],
    payload: GenericConfigUpdate,
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    scheduler: Annotated[SyncScheduler, Depends(get_sync_scheduler)],
) -> ConfigUpdatedResponse:
    """Update the sync interval for any registered connector."""
    if registry.get(name) is None:
        raise HTTPException(status_code=404, detail=f"Connector '{name}' not registered")

    scheduler.reschedule_connector(name, payload.sync_interval_minutes * 60)
    log.info(
        "connector_config_updated",
        connector=name,
        sync_interval_minutes=payload.sync_interval_minutes,
    )
    return ConfigUpdatedResponse(sync_interval_minutes=payload.sync_interval_minutes)


@generic_router.post("/{name}/authenticate")
async def generic_authenticate(
    name: Annotated[str, Path(pattern=_CONNECTOR_NAME_PATTERN)],
    background_tasks: BackgroundTasks,
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
) -> MSDeviceCodeResponse:
    """Initiate MS device-code auth for any MS-capable connector."""
    connector = registry.get(name)
    if connector is None:
        raise HTTPException(status_code=404, detail=f"Connector '{name}' not registered")

    if not isinstance(connector, MSAuthConnector):
        raise HTTPException(
            status_code=400,
            detail=f"Connector '{name}' does not support MS authentication",
        )

    try:
        info, context = await connector.initiate_auth_flow()
    except (RuntimeError, ValueError) as exc:
        log.error("ms_auth.initiate_failed", connector=name, error=str(exc))
        raise HTTPException(
            status_code=500, detail="Authentication flow could not be initiated"
        ) from exc

    background_tasks.add_task(_poll_for_ms_token, connector, context, name)

    log.info(
        "ms_auth.device_flow_initiated",
        connector=name,
        verification_uri=info.verification_uri,
    )
    return MSDeviceCodeResponse(
        user_code=info.user_code,
        verification_uri=info.verification_uri,
        expires_in=info.expires_in,
        message=info.message,
    )
