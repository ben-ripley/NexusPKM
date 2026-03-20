"""Dashboard API endpoints.

Provides activity feed, knowledge base stats, and upcoming items for the
dashboard home page.

Spec: F-008
NXP-65
"""

from __future__ import annotations

from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, BaseModel

from nexuspkm.api.engine import get_knowledge_index
from nexuspkm.engine.index import KnowledgeIndex

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ActivityItem(BaseModel):
    id: str
    type: Literal[
        "document_ingested",
        "entity_discovered",
        "relationship_created",
        "sync_completed",
    ]
    title: str
    description: str
    source_type: str | None = None
    timestamp: AwareDatetime


class DashboardActivityResponse(BaseModel):
    items: list[ActivityItem]


class DashboardStatsResponse(BaseModel):
    total_documents: int
    total_chunks: int
    total_entities: int
    total_relationships: int
    by_source_type: dict[str, int]


class UpcomingItem(BaseModel):
    id: str
    title: str
    starts_at: AwareDatetime
    meeting_prep_available: bool
    action_items: list[str]


class DashboardUpcomingResponse(BaseModel):
    items: list[UpcomingItem]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/activity")
async def get_activity() -> DashboardActivityResponse:
    """Return recent activity items.

    Stub: returns empty list until an activity log is implemented in a later phase.
    """
    return DashboardActivityResponse(items=[])


@router.get("/stats")
async def get_stats(
    index: Annotated[KnowledgeIndex, Depends(get_knowledge_index)],
) -> DashboardStatsResponse:
    """Return knowledge base statistics aggregated from the index."""
    try:
        raw = await index.stats()
    except Exception as exc:
        log.error("dashboard_stats_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to retrieve dashboard stats") from exc

    return DashboardStatsResponse(
        total_documents=raw.get("documents", 0),
        total_chunks=raw.get("chunks", 0),
        total_entities=raw.get("entities", 0),
        total_relationships=raw.get("relationships", 0),
        by_source_type={},
    )


@router.get("/upcoming")
async def get_upcoming() -> DashboardUpcomingResponse:
    """Return upcoming calendar items.

    Stub: returns empty list until a calendar connector is implemented.
    """
    return DashboardUpcomingResponse(items=[])
