"""EntityDeduplicator — resolve extracted entities against the existing graph.

Resolution order (highest priority first):
1. Email match (Person only): exact email → same entity
2. Exact name match: case-insensitive canonical name
3. Fuzzy name match: Levenshtein distance ≤ 2
4. LLM-assisted: only when llm_provider is set and distance is in ambiguous range

When a match is found, the new name variant is added as an alias.

Spec: F-006 FR-4
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import structlog

from nexuspkm.engine.graph_store import GraphStore
from nexuspkm.models.entity import EntityType, ExtractedEntity
from nexuspkm.providers.base import BaseLLMProvider

logger = structlog.get_logger(__name__)

# Levenshtein threshold for fuzzy matching — distance must be ≤ this value.
_FUZZY_THRESHOLD = 2
# Levenshtein range where LLM-assisted confirmation is attempted (lower bound exclusive).
_LLM_LOWER = 2
_LLM_UPPER = 5

# Node table to query for each entity type
_ENTITY_TYPE_TABLE: dict[EntityType, str] = {
    EntityType.PERSON: "Person",
    EntityType.PROJECT: "Project",
    EntityType.TOPIC: "Topic",
    EntityType.DECISION: "Decision",
    EntityType.ACTION_ITEM: "ActionItem",
    EntityType.MEETING: "Meeting",
}

# The Kuzu property that holds the canonical display name for each node type.
# Kept in sync with the schema in graph_store.py.
_ENTITY_NAME_FIELD: dict[EntityType, str] = {
    EntityType.PERSON: "name",
    EntityType.PROJECT: "name",
    EntityType.TOPIC: "name",
    EntityType.DECISION: "summary",
    EntityType.ACTION_ITEM: "description",
    EntityType.MEETING: "title",
}

# Node types whose Kuzu schema includes an `aliases STRING[]` property.
_ENTITY_TYPES_WITH_ALIASES: frozenset[EntityType] = frozenset(
    {EntityType.PERSON, EntityType.PROJECT}
)

# Whitelist of valid Kuzu node label strings used in f-string query construction.
_ALLOWED_NODE_LABELS: frozenset[str] = frozenset(_ENTITY_TYPE_TABLE.values())


def _levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein edit distance between two strings (DP, O(len(a)*len(b)))."""
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            tmp = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = tmp
    return dp[n]


class EntityDeduplicator:
    """Match extracted entities against existing graph nodes.

    All Kuzu calls are synchronous and must be executed inside a thread-pool
    executor under the shared graph_lock (same pattern as IngestionPipeline).
    """

    def __init__(
        self,
        graph_store: GraphStore,
        graph_lock: threading.Lock,
        llm_provider: BaseLLMProvider | None = None,
    ) -> None:
        self._graph_store = graph_store
        self._graph_lock = graph_lock
        self._llm = llm_provider

    async def find_match(self, entity: ExtractedEntity) -> str | None:
        """Return existing entity ID or None.

        Adds new name variant as alias when a match is found.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._find_match_sync, entity)

    # ------------------------------------------------------------------
    # Sync helpers (executed in thread pool under lock)
    # ------------------------------------------------------------------

    def _find_match_sync(self, entity: ExtractedEntity) -> str | None:
        with self._graph_lock:
            return self._resolve(entity)

    def _resolve(self, entity: ExtractedEntity) -> str | None:
        table = _ENTITY_TYPE_TABLE.get(entity.type)
        if table is None:
            return None
        if table not in _ALLOWED_NODE_LABELS:
            raise ValueError(f"Unexpected node label: {table!r}")

        name_field = _ENTITY_NAME_FIELD.get(entity.type, "name")
        has_aliases = entity.type in _ENTITY_TYPES_WITH_ALIASES
        # Fetch existing nodes for this entity type — only query columns present in schema
        if entity.type == EntityType.PERSON:
            rows = self._graph_store.execute(
                f"MATCH (n:{table}) RETURN n.id, n.{name_field} AS name, n.email, n.aliases"
            )
        elif has_aliases:
            rows = self._graph_store.execute(
                f"MATCH (n:{table}) RETURN n.id, n.{name_field} AS name, n.aliases"
            )
        else:
            rows = self._graph_store.execute(
                f"MATCH (n:{table}) RETURN n.id, n.{name_field} AS name"
            )

        # 1. Email match (Person only)
        if entity.type == EntityType.PERSON:
            new_email = str(entity.properties.get("email", "")).strip().lower()
            if new_email:
                for row in rows:
                    existing_email = str(row.get("n.email") or "").strip().lower()
                    if existing_email and existing_email == new_email:
                        self._add_alias(table, row["n.id"], row, entity.name)
                        logger.debug(
                            "dedup.email_match",
                            entity=entity.name,
                            match_id=row["n.id"],
                        )
                        return str(row["n.id"])

        # 2. Exact name match (case-insensitive)
        entity_name_lower = entity.name.strip().lower()
        for row in rows:
            if row["name"].strip().lower() == entity_name_lower:
                self._add_alias(table, row["n.id"], row, entity.name)
                logger.debug(
                    "dedup.exact_match",
                    entity=entity.name,
                    match_id=row["n.id"],
                )
                return str(row["n.id"])

        # 3. Fuzzy name match (Levenshtein ≤ threshold)
        for row in rows:
            dist = _levenshtein(entity_name_lower, row["name"].strip().lower())
            if dist <= _FUZZY_THRESHOLD:
                self._add_alias(table, row["n.id"], row, entity.name)
                logger.debug(
                    "dedup.fuzzy_match",
                    entity=entity.name,
                    match_id=row["n.id"],
                    distance=dist,
                )
                return str(row["n.id"])

        # 4. LLM-assisted (ambiguous range — async not possible here, skip in sync context)
        # LLM-assisted dedup is handled separately by callers that can await.
        return None

    def _add_alias(
        self,
        table: str,
        node_id: str,
        row: dict[str, Any],
        new_name: str,
    ) -> None:
        """Add new_name as an alias if not already present.

        Only runs the SET query for node types whose schema includes an
        ``aliases STRING[]`` column (Person, Project). Other types silently skip.
        """
        _tables_with_aliases = frozenset(_ENTITY_TYPE_TABLE[t] for t in _ENTITY_TYPES_WITH_ALIASES)
        if table not in _tables_with_aliases:
            return
        existing_aliases: list[str] = list(row.get("n.aliases") or [])
        canonical = row["name"]
        if new_name != canonical and new_name not in existing_aliases:
            existing_aliases.append(new_name)
            self._graph_store.execute(
                f"MATCH (n:{table} {{id: $id}}) SET n.aliases = $aliases",
                {"id": node_id, "aliases": existing_aliases},
            )
