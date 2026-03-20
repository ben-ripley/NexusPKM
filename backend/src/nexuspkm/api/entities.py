"""Entity intelligence API endpoints.

Exposes:
  GET  /api/entities              list entities with type/name filtering
  GET  /api/entities/{id}         entity detail + relationships
  POST /api/entities/merge        merge two entities (manual dedup override)
  GET  /api/relationships         list relationships with type/entity_id filtering
  GET  /api/extraction/status     extraction queue status
  GET  /api/contradictions        list unresolved contradictions
  POST /api/contradictions/{id}/resolve  mark contradiction resolved

Spec: F-006 API endpoints
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from nexuspkm.engine.contradiction import ContradictionDetector
from nexuspkm.engine.extraction_queue import ExtractionQueue
from nexuspkm.engine.graph_store import _REL_TABLE_MAP, GraphStore  # noqa: PLC2701
from nexuspkm.models.contradiction import ContradictionType, QueueStatus
from nexuspkm.models.entity import EntityType

log = structlog.get_logger(__name__)

router = APIRouter(tags=["entities"])

# ---------------------------------------------------------------------------
# Dependency providers (overridden in main.py lifespan)
# ---------------------------------------------------------------------------


def get_graph_store() -> GraphStore:
    """Dependency: returns the active GraphStore."""
    raise HTTPException(  # pragma: no cover
        status_code=503, detail="Graph store not initialised"
    )


def get_extraction_queue() -> ExtractionQueue:
    """Dependency: returns the active ExtractionQueue."""
    raise HTTPException(  # pragma: no cover
        status_code=503, detail="Extraction queue not initialised"
    )


def get_contradiction_detector() -> ContradictionDetector:
    """Dependency: returns the shared ContradictionDetector instance."""
    raise HTTPException(  # pragma: no cover
        status_code=503, detail="Contradiction detector not initialised"
    )


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class EntityResponse(BaseModel):
    id: str
    name: str
    entity_type: EntityType
    properties: dict[str, Any] = Field(default_factory=dict)


class EntityDetailResponse(EntityResponse):
    relationships: list[dict[str, str]] = Field(default_factory=list)


class MergeRequest(BaseModel):
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)


class MergeResponse(BaseModel):
    status: Literal["merged"] = "merged"
    target_id: str


class RelationshipResponse(BaseModel):
    rel_type: str
    from_id: str
    to_id: str


class ContradictionResponse(BaseModel):
    id: str
    entity_id: str
    field_name: str
    old_value: str
    new_value: str
    source_doc_id: str
    detected_at: str
    contradiction_type: ContradictionType
    resolved: bool


class ResolveResponse(BaseModel):
    status: Literal["resolved"] = "resolved"


# ---------------------------------------------------------------------------
# Node table mapping for entity queries
# ---------------------------------------------------------------------------

_TYPE_TABLE: dict[EntityType, str] = {
    EntityType.PERSON: "Person",
    EntityType.PROJECT: "Project",
    EntityType.TOPIC: "Topic",
    EntityType.DECISION: "Decision",
    EntityType.ACTION_ITEM: "ActionItem",
    EntityType.MEETING: "Meeting",
}

_ALL_TABLES = list(_TYPE_TABLE.items())

# Whitelist of valid Kuzu node label strings — used to guard f-string query construction.
_ALLOWED_NODE_LABELS: frozenset[str] = frozenset(_TYPE_TABLE.values())

# Fields to return per node type
_TYPE_NAME_FIELD: dict[str, str] = {
    "Person": "name",
    "Project": "name",
    "Topic": "name",
    "Decision": "summary",
    "ActionItem": "description",
    "Meeting": "title",
}


# ---------------------------------------------------------------------------
# GET /api/entities
# ---------------------------------------------------------------------------


@router.get("/api/entities", response_model=list[EntityResponse])
async def list_entities(
    graph_store: Annotated[GraphStore, Depends(get_graph_store)],
    type: EntityType | None = None,
    name: str | None = None,
) -> list[EntityResponse]:
    """List entities with optional type and name (substring) filters."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _list_entities_sync, graph_store, type, name)


def _list_entities_sync(
    graph_store: GraphStore,
    entity_type: EntityType | None,
    name_filter: str | None,
) -> list[EntityResponse]:
    tables = [(entity_type, _TYPE_TABLE[entity_type])] if entity_type is not None else _ALL_TABLES
    results: list[EntityResponse] = []
    for etype, table in tables:
        assert table in _ALLOWED_NODE_LABELS, f"Unexpected node label: {table!r}"
        name_field = _TYPE_NAME_FIELD[table]
        rows = graph_store.execute(f"MATCH (n:{table}) RETURN n.id AS id, n.{name_field} AS name")
        for row in rows:
            entity_name: str = row.get("name") or ""
            if name_filter and name_filter.lower() not in entity_name.lower():
                continue
            results.append(EntityResponse(id=row["id"], name=entity_name, entity_type=etype))
    return results


# ---------------------------------------------------------------------------
# GET /api/entities/merge  (must be declared BEFORE /{id} to avoid conflict)
# ---------------------------------------------------------------------------


@router.post("/api/entities/merge", response_model=MergeResponse)
async def merge_entities(
    payload: MergeRequest,
    graph_store: Annotated[GraphStore, Depends(get_graph_store)],
) -> MergeResponse:
    """Merge source entity into target (manual dedup override).

    Removes the source entity node. The target node is preserved.
    """
    loop = asyncio.get_running_loop()
    found = await loop.run_in_executor(
        None, _merge_entities_sync, graph_store, payload.source_id, payload.target_id
    )
    if not found:
        raise HTTPException(status_code=404, detail="Source entity not found")
    log.info("entities.merged", source=payload.source_id, target=payload.target_id)
    return MergeResponse(target_id=payload.target_id)


def _merge_entities_sync(graph_store: GraphStore, source_id: str, target_id: str) -> bool:
    """Migrate source node's relationships to target, then delete source.

    Returns True if source was found (and deleted), False if not found.
    """
    source_table: str | None = None
    for table in _TYPE_TABLE.values():
        assert table in _ALLOWED_NODE_LABELS, f"Unexpected node label: {table!r}"
        rows = graph_store.execute(f"MATCH (n:{table} {{id: $id}}) RETURN n.id", {"id": source_id})
        if rows:
            source_table = table
            break
    if source_table is None:
        return False

    # Migrate relationships before deleting source to avoid orphaning graph edges.
    for rel_type, (from_t, to_t) in _REL_TABLE_MAP.items():
        if from_t == source_table:
            for rel in graph_store.get_relationships(rel_type, from_id=source_id):
                with contextlib.suppress(Exception):
                    graph_store.create_relationship(rel_type, from_t, target_id, to_t, rel["to_id"])
        if to_t == source_table:
            for rel in graph_store.get_relationships(rel_type, to_id=source_id):
                with contextlib.suppress(Exception):
                    graph_store.create_relationship(
                        rel_type, from_t, rel["from_id"], to_t, target_id
                    )

    graph_store.delete_node(source_table, source_id)
    return True


# ---------------------------------------------------------------------------
# GET /api/entities/{id}
# ---------------------------------------------------------------------------


@router.get("/api/entities/{entity_id}", response_model=EntityDetailResponse)
async def get_entity(
    entity_id: str,
    graph_store: Annotated[GraphStore, Depends(get_graph_store)],
) -> EntityDetailResponse:
    """Return entity detail including its relationships."""
    loop = asyncio.get_running_loop()
    entity = await loop.run_in_executor(None, _get_entity_sync, graph_store, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


def _get_entity_sync(graph_store: GraphStore, entity_id: str) -> EntityDetailResponse | None:
    for etype, table in _ALL_TABLES:
        assert table in _ALLOWED_NODE_LABELS, f"Unexpected node label: {table!r}"
        name_field = _TYPE_NAME_FIELD[table]
        rows = graph_store.execute(
            f"MATCH (n:{table} {{id: $id}}) RETURN n.id AS id, n.{name_field} AS name",
            {"id": entity_id},
        )
        if not rows:
            continue
        row = rows[0]
        # Fetch relationships where this entity is the source
        rels: list[dict[str, str]] = []
        for rel_type, (from_t, _to_t) in _REL_TABLE_MAP.items():
            if from_t == table:
                rel_rows = graph_store.get_relationships(rel_type, from_id=entity_id)
                for rr in rel_rows:
                    rels.append(
                        {"rel_type": rel_type, "from_id": rr["from_id"], "to_id": rr["to_id"]}
                    )
        return EntityDetailResponse(
            id=row["id"],
            name=row.get("name") or "",
            entity_type=etype,
            relationships=rels,
        )
    return None


# ---------------------------------------------------------------------------
# GET /api/relationships
# ---------------------------------------------------------------------------


@router.get("/api/relationships", response_model=list[RelationshipResponse])
async def list_relationships(
    graph_store: Annotated[GraphStore, Depends(get_graph_store)],
    type: str | None = None,
    entity_id: str | None = None,
) -> list[RelationshipResponse]:
    """List relationships with optional rel_type and entity_id filters."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _list_relationships_sync, graph_store, type, entity_id)


def _list_relationships_sync(
    graph_store: GraphStore,
    rel_type_filter: str | None,
    entity_id_filter: str | None,
) -> list[RelationshipResponse]:
    rel_types = (
        [rel_type_filter]
        if rel_type_filter and rel_type_filter in _REL_TABLE_MAP
        else list(_REL_TABLE_MAP.keys())
    )
    results: list[RelationshipResponse] = []
    for rel_type in rel_types:
        rows = graph_store.get_relationships(
            rel_type,
            from_id=entity_id_filter,
        )
        for row in rows:
            results.append(
                RelationshipResponse(
                    rel_type=rel_type,
                    from_id=row["from_id"],
                    to_id=row["to_id"],
                )
            )
    return results


# ---------------------------------------------------------------------------
# GET /api/extraction/status
# ---------------------------------------------------------------------------


@router.get("/api/extraction/status", response_model=QueueStatus)
async def extraction_status(
    queue: Annotated[ExtractionQueue, Depends(get_extraction_queue)],
) -> QueueStatus:
    """Return extraction queue status counts."""
    return await queue.status()


# ---------------------------------------------------------------------------
# GET /api/contradictions
# ---------------------------------------------------------------------------


@router.get("/api/contradictions", response_model=list[ContradictionResponse])
async def list_contradictions(
    detector: Annotated[ContradictionDetector, Depends(get_contradiction_detector)],
) -> list[ContradictionResponse]:
    """Return all unresolved contradictions."""
    items = await detector.list_unresolved()
    return [
        ContradictionResponse(
            id=c.id,
            entity_id=c.entity_id,
            field_name=c.field_name,
            old_value=c.old_value,
            new_value=c.new_value,
            source_doc_id=c.source_doc_id,
            detected_at=c.detected_at.isoformat(),
            contradiction_type=c.contradiction_type,
            resolved=c.resolved,
        )
        for c in items
    ]


# ---------------------------------------------------------------------------
# POST /api/contradictions/{id}/resolve
# ---------------------------------------------------------------------------


@router.post("/api/contradictions/{contradiction_id}/resolve", response_model=ResolveResponse)
async def resolve_contradiction(
    contradiction_id: str,
    detector: Annotated[ContradictionDetector, Depends(get_contradiction_detector)],
) -> ResolveResponse:
    """Mark a contradiction as resolved."""
    found = await detector.resolve(contradiction_id)
    if not found:
        raise HTTPException(status_code=404, detail="Contradiction not found")
    log.info("contradiction.resolved", id=contradiction_id)
    return ResolveResponse()
