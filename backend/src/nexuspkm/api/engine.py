"""Knowledge engine API endpoints."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from nexuspkm.engine.index import KnowledgeIndex
from nexuspkm.models.document import Document

log = structlog.get_logger()

router = APIRouter(prefix="/api/engine", tags=["engine"])


class EngineStats(BaseModel):
    documents: int
    chunks: int
    entities: int
    relationships: int


class EngineStatus(BaseModel):
    status: str
    queue_size: int


class ReindexRequest(BaseModel):
    full: bool = False


class ReindexResponse(BaseModel):
    status: str
    reindexed: int


def get_knowledge_index() -> KnowledgeIndex:
    """Dependency: returns the active KnowledgeIndex.

    Replaced via app.dependency_overrides in main.py's lifespan.
    """
    raise HTTPException(status_code=503, detail="Knowledge index not initialised")


@router.post("/ingest")
async def ingest_document(
    document: Document,
    index: Annotated[KnowledgeIndex, Depends(get_knowledge_index)],
) -> Document:
    try:
        return await index.insert(document)
    except Exception as exc:
        log.error("engine_ingest_failed", document_id=document.id, error=str(exc))
        raise HTTPException(status_code=500, detail="Ingestion failed") from exc


@router.get("/stats")
async def get_stats(
    index: Annotated[KnowledgeIndex, Depends(get_knowledge_index)],
) -> EngineStats:
    try:
        raw = await index.stats()
        return EngineStats(**raw)
    except Exception as exc:
        log.error("engine_stats_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to retrieve engine stats") from exc


@router.get("/status")
async def get_status(
    index: Annotated[KnowledgeIndex, Depends(get_knowledge_index)],
) -> EngineStatus:
    # TODO: return real extraction queue depth once the queue is implemented (NXP-5x).
    # `index` is intentionally kept as a dependency so this endpoint returns 503
    # when the engine is unavailable, consistent with all other engine endpoints.
    return EngineStatus(status="idle", queue_size=0)


@router.post("/reindex")
async def reindex(
    request: ReindexRequest,
    index: Annotated[KnowledgeIndex, Depends(get_knowledge_index)],
) -> ReindexResponse:
    # TODO: implement full reindex once the raw-document store is available (NXP-5x).
    return ReindexResponse(status="completed", reindexed=0)
