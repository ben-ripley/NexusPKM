"""Provider management API endpoints."""

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException

from nexuspkm.config.models import ProvidersConfig
from nexuspkm.providers.registry import ProviderRegistry

log = structlog.get_logger()

router = APIRouter(prefix="/api/providers", tags=["providers"])


def get_registry() -> ProviderRegistry:
    """Dependency: returns the active ProviderRegistry.

    This function is replaced via app.dependency_overrides in main.py's lifespan.
    """
    raise NotImplementedError("ProviderRegistry not initialised")  # pragma: no cover


@router.get("/health")
async def get_health(
    registry: Annotated[ProviderRegistry, Depends(get_registry)],
) -> dict[str, Any]:
    health = await registry.check_health()
    return {k: v.model_dump() for k, v in health.items()}


@router.get("/active")
async def get_active(
    registry: Annotated[ProviderRegistry, Depends(get_registry)],
) -> dict[str, Any]:
    return {
        "llm": {
            "provider": registry._config.llm.primary.provider,
            "model": registry._config.llm.primary.model,
        },
        "embedding": {
            "provider": registry._config.embedding.primary.provider,
            "model": registry._config.embedding.primary.model,
        },
    }


@router.put("/config")
async def update_config(
    payload: ProvidersConfig,
    registry: Annotated[ProviderRegistry, Depends(get_registry)],
) -> dict[str, str]:
    try:
        registry.reload(payload)
    except Exception as exc:
        log.error("provider_config_reload_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    log.info(
        "provider_config_updated",
        llm=payload.llm.primary.provider,
        embedding=payload.embedding.primary.provider,
    )
    return {"status": "reloaded"}
