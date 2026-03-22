"""Schedule & Task Management API endpoints.

Exposes:
  GET /api/schedule/digest            - daily digest (optional ?date= param)
  GET /api/schedule/action-items      - prioritized action items
  GET /api/schedule/team-workload     - team workload view
  GET /api/schedule/overlaps          - overlap/conflict alerts

Spec: F-012
NXP-86
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException

from nexuspkm.models.schedule import (
    DailyDigest,
    OverlapAlert,
    PrioritizedItem,
    TeamWorkload,
)
from nexuspkm.services.schedule import ScheduleService

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


# ---------------------------------------------------------------------------
# Dependency provider (overridden in main.py lifespan)
# ---------------------------------------------------------------------------


def get_schedule_service() -> ScheduleService:
    """Dependency: returns the active ScheduleService."""
    raise HTTPException(  # pragma: no cover
        status_code=503, detail="Schedule service not initialised"
    )


# ---------------------------------------------------------------------------
# GET /api/schedule/digest
# ---------------------------------------------------------------------------


@router.get("/digest", response_model=DailyDigest)
async def get_digest(
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
    date: date | None = None,
) -> DailyDigest:
    """Generate the daily digest, optionally for a specific date."""
    log.info("schedule.digest_requested", date=str(date))
    return await service.get_daily_digest(for_date=date)


# ---------------------------------------------------------------------------
# GET /api/schedule/action-items
# ---------------------------------------------------------------------------


@router.get("/action-items", response_model=list[PrioritizedItem])
async def get_action_items(
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> list[PrioritizedItem]:
    """Return all open action items ranked by priority score."""
    return await service.get_prioritized_action_items()


# ---------------------------------------------------------------------------
# GET /api/schedule/team-workload
# ---------------------------------------------------------------------------


@router.get("/team-workload", response_model=TeamWorkload)
async def get_team_workload(
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> TeamWorkload:
    """Return per-person workload metrics and overlap alerts."""
    return await service.get_team_workload()


# ---------------------------------------------------------------------------
# GET /api/schedule/overlaps
# ---------------------------------------------------------------------------


@router.get("/overlaps", response_model=list[OverlapAlert])
async def get_overlaps(
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> list[OverlapAlert]:
    """Return detected topic/workload overlap alerts."""
    return await service.get_overlaps()
