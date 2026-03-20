"""EntityExtractionPipeline — orchestrates the full extraction pipeline.

Steps for each document:
1. Extract entities + relationships (via EntityExtractor → LLM)
2. Deduplicate each entity against existing graph nodes
3. Upsert new/matched entities in Kuzu
4. Create relationships in Kuzu
5. Detect contradictions vs existing data, persist to SQLite
6. Log completion

Spec: F-006 FR-2
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from nexuspkm.engine.contradiction import ContradictionDetector
from nexuspkm.engine.deduplication import EntityDeduplicator
from nexuspkm.engine.extraction import EntityExtractor
from nexuspkm.engine.graph_store import (
    ActionItemNode,
    DecisionNode,
    GraphStore,
    MeetingNode,
    PersonNode,
    ProjectNode,
    TopicNode,
)
from nexuspkm.models.document import Document
from nexuspkm.models.entity import EntityType, ExtractedEntity, ExtractedRelationship

logger = structlog.get_logger(__name__)


class EntityExtractionPipeline:
    """Full extraction pipeline: document → entities → dedup → graph → contradictions."""

    def __init__(
        self,
        extractor: EntityExtractor,
        deduplicator: EntityDeduplicator,
        graph_store: GraphStore,
        graph_lock: threading.Lock,
        contradiction_detector: ContradictionDetector,
    ) -> None:
        self._extractor = extractor
        self._deduplicator = deduplicator
        self._graph_store = graph_store
        self._graph_lock = graph_lock
        self._contradiction_detector = contradiction_detector

    async def process(self, document: Document) -> None:
        """Run the full pipeline for one document."""
        log = logger.bind(document_id=document.id)
        log.info("entity_pipeline.start")

        # 1. Extract
        result = await self._extractor.extract(document.content, document.id)

        if not result.entities and not result.relationships:
            log.info("entity_pipeline.empty_extraction")
            return

        # 2. Deduplicate + upsert entities
        # Build a name→id map so relationship creation can resolve entity names
        entity_name_to_id: dict[str, str] = {}

        for entity in result.entities:
            existing_id = await self._deduplicator.find_match(entity)
            if existing_id is not None:
                entity_name_to_id[entity.name] = existing_id
                # Detect contradictions against existing data
                await self._check_contradictions(entity, existing_id, document.id)
            else:
                new_id = str(uuid.uuid4())
                entity_name_to_id[entity.name] = new_id
                await self._upsert_entity(entity, new_id)

        # 3. Create relationships
        for rel in result.relationships:
            await self._create_relationship(rel, entity_name_to_id)

        log.info(
            "entity_pipeline.complete",
            entities=len(result.entities),
            relationships=len(result.relationships),
        )

    # ------------------------------------------------------------------
    # Entity upsert (sync helpers run in executor under lock)
    # ------------------------------------------------------------------

    async def _upsert_entity(self, entity: ExtractedEntity, entity_id: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._upsert_entity_sync, entity, entity_id)

    def _upsert_entity_sync(self, entity: ExtractedEntity, entity_id: str) -> None:
        props = dict(entity.properties)
        with self._graph_lock:
            if entity.type == EntityType.PERSON:
                self._graph_store.upsert_person(
                    PersonNode(
                        id=entity_id,
                        name=entity.name,
                        email=str(props.get("email", "")),
                        aliases=[],
                        first_seen=datetime.now(tz=UTC),
                        last_seen=datetime.now(tz=UTC),
                    )
                )
            elif entity.type == EntityType.PROJECT:
                self._graph_store.upsert_project(
                    ProjectNode(
                        id=entity_id,
                        name=entity.name,
                        description=str(props.get("description", "")),
                        aliases=[],
                    )
                )
            elif entity.type == EntityType.TOPIC:
                raw_kw = props.get("keywords")
                keywords: list[str] = list(raw_kw) if isinstance(raw_kw, list) else []
                self._graph_store.upsert_topic(
                    TopicNode(
                        id=entity_id,
                        name=entity.name,
                        keywords=keywords,
                    )
                )
            elif entity.type == EntityType.DECISION:
                self._graph_store.upsert_decision(
                    DecisionNode(
                        id=entity_id,
                        summary=entity.name,
                        context=str(props.get("context", "")),
                    )
                )
            elif entity.type == EntityType.ACTION_ITEM:
                self._graph_store.upsert_action_item(
                    ActionItemNode(
                        id=entity_id,
                        description=entity.name,
                        status=str(props.get("status", "open")),
                        assignee_id=str(props.get("assignee_id", "")),
                    )
                )
            elif entity.type == EntityType.MEETING:
                raw_dur = props.get("duration_minutes", 0)
                duration_minutes = int(raw_dur) if isinstance(raw_dur, (int, float)) else 0
                self._graph_store.upsert_meeting(
                    MeetingNode(
                        id=entity_id,
                        title=entity.name,
                        duration_minutes=duration_minutes,
                    )
                )

    # ------------------------------------------------------------------
    # Relationship creation
    # ------------------------------------------------------------------

    async def _create_relationship(
        self,
        rel: ExtractedRelationship,
        entity_name_to_id: dict[str, str],
    ) -> None:
        from_id = entity_name_to_id.get(rel.source_entity)
        to_id = entity_name_to_id.get(rel.target_entity)
        if from_id is None or to_id is None:
            logger.debug(
                "entity_pipeline.relationship_skip",
                source=rel.source_entity,
                target=rel.target_entity,
                reason="entity not found in name map",
            )
            return

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._create_relationship_sync, rel, from_id, to_id)

    def _create_relationship_sync(
        self,
        rel: ExtractedRelationship,
        from_id: str,
        to_id: str,
    ) -> None:
        from nexuspkm.engine.graph_store import _REL_TABLE_MAP  # noqa: PLC2701

        rel_type = rel.relationship_type.value
        if rel_type not in _REL_TABLE_MAP:
            logger.warning("entity_pipeline.unknown_rel_type", rel_type=rel_type)
            return

        from_table, to_table = _REL_TABLE_MAP[rel_type]
        with self._graph_lock:
            try:
                self._graph_store.create_relationship(
                    rel_type=rel_type,
                    from_table=from_table,
                    from_id=from_id,
                    to_table=to_table,
                    to_id=to_id,
                )
            except Exception as exc:
                logger.warning(
                    "entity_pipeline.relationship_create_failed",
                    rel_type=rel_type,
                    from_id=from_id,
                    to_id=to_id,
                    error=str(exc),
                )

    # ------------------------------------------------------------------
    # Contradiction detection
    # ------------------------------------------------------------------

    async def _check_contradictions(
        self,
        entity: ExtractedEntity,
        existing_id: str,
        source_doc_id: str,
    ) -> None:
        """Fetch existing properties and check for conflicts."""
        loop = asyncio.get_running_loop()
        existing_props = await loop.run_in_executor(
            None, self._fetch_entity_properties_sync, entity.type, existing_id
        )
        if not existing_props:
            return

        contradictions = await self._contradiction_detector.detect(
            entity_id=existing_id,
            existing_properties=existing_props,
            new_properties=dict(entity.properties),
            source_doc_id=source_doc_id,
        )
        if contradictions:
            await self._contradiction_detector.persist(contradictions)
            logger.info(
                "entity_pipeline.contradictions_detected",
                entity_id=existing_id,
                count=len(contradictions),
            )

    def _fetch_entity_properties_sync(
        self, entity_type: EntityType, entity_id: str
    ) -> dict[str, Any]:
        """Fetch mutable properties of an existing entity as a flat dict."""
        with self._graph_lock:
            if entity_type == EntityType.PROJECT:
                rows = self._graph_store.execute(
                    "MATCH (n:Project {id: $id}) RETURN n.name, n.description",
                    {"id": entity_id},
                )
                if rows:
                    r = rows[0]
                    props: dict[str, Any] = {}
                    if r.get("n.description"):
                        props["description"] = r["n.description"]
                    # Add status from description if encoded — simplified approach
                    return props
            elif entity_type == EntityType.ACTION_ITEM:
                rows = self._graph_store.execute(
                    "MATCH (n:ActionItem {id: $id}) RETURN n.status, n.due_date, n.assignee_id",
                    {"id": entity_id},
                )
                if rows:
                    r = rows[0]
                    result: dict[str, Any] = {}
                    if r.get("n.status"):
                        result["status"] = r["n.status"]
                    if r.get("n.due_date"):
                        result["due_date"] = str(r["n.due_date"])
                    if r.get("n.assignee_id"):
                        result["assignee_id"] = r["n.assignee_id"]
                    return result
        return {}
