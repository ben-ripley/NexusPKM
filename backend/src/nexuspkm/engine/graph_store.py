"""Kuzu graph database store.

Provides GraphStore — the single access point for all graph storage and
entity/relationship operations in NexusPKM.

All methods are synchronous (Kuzu is a sync C++ extension). Async wrapping
for use from FastAPI handlers is deferred to the service layer (NXP-38+).

**Thread safety**: a single ``kuzu.Connection`` is NOT safe to share across
threads or concurrent asyncio tasks. The service layer (NXP-38+) is responsible
for either creating per-request connections or serialising access with a lock.

Spec: F-002 FR-4
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import kuzu
import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Node models
# ---------------------------------------------------------------------------


class PersonNode(BaseModel):
    id: str
    name: str
    email: str = ""
    aliases: list[str] = []
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class ProjectNode(BaseModel):
    id: str
    name: str
    description: str = ""
    aliases: list[str] = []


class TopicNode(BaseModel):
    id: str
    name: str
    keywords: list[str] = []


class DecisionNode(BaseModel):
    id: str
    summary: str
    made_at: datetime | None = None
    context: str = ""


class ActionItemNode(BaseModel):
    id: str
    description: str
    status: str = "open"
    due_date: datetime | None = None
    assignee_id: str = ""


class MeetingNode(BaseModel):
    id: str
    title: str
    date: datetime | None = None
    duration_minutes: int = 0
    source_id: str = ""


class DocumentNode(BaseModel):
    id: str
    title: str
    source_type: str = ""
    source_id: str = ""
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_NODE_DDL: list[str] = [
    (
        "CREATE NODE TABLE IF NOT EXISTS Person("
        "id STRING, name STRING, email STRING, aliases STRING[], "
        "first_seen TIMESTAMP, last_seen TIMESTAMP, PRIMARY KEY (id))"
    ),
    (
        "CREATE NODE TABLE IF NOT EXISTS Project("
        "id STRING, name STRING, description STRING, aliases STRING[], "
        "PRIMARY KEY (id))"
    ),
    (
        "CREATE NODE TABLE IF NOT EXISTS Topic("
        "id STRING, name STRING, keywords STRING[], PRIMARY KEY (id))"
    ),
    (
        "CREATE NODE TABLE IF NOT EXISTS Decision("
        "id STRING, summary STRING, made_at TIMESTAMP, context STRING, "
        "PRIMARY KEY (id))"
    ),
    (
        "CREATE NODE TABLE IF NOT EXISTS ActionItem("
        "id STRING, description STRING, status STRING, due_date TIMESTAMP, "
        "assignee_id STRING, PRIMARY KEY (id))"
    ),
    (
        "CREATE NODE TABLE IF NOT EXISTS Meeting("
        "id STRING, title STRING, date TIMESTAMP, duration_minutes INT32, "
        "source_id STRING, PRIMARY KEY (id))"
    ),
    (
        "CREATE NODE TABLE IF NOT EXISTS Document("
        "id STRING, title STRING, source_type STRING, source_id STRING, "
        "created_at TIMESTAMP, PRIMARY KEY (id))"
    ),
]

_REL_DDL: list[str] = [
    "CREATE REL TABLE IF NOT EXISTS ATTENDED(FROM Person TO Meeting)",
    "CREATE REL TABLE IF NOT EXISTS MENTIONED_IN(FROM Person TO Document, context STRING)",
    "CREATE REL TABLE IF NOT EXISTS ASSIGNED_TO(FROM ActionItem TO Person)",
    (
        "CREATE REL TABLE IF NOT EXISTS RELATED_TO("
        "FROM Document TO Document, relationship STRING, confidence FLOAT)"
    ),
    "CREATE REL TABLE IF NOT EXISTS DECIDED_IN(FROM Decision TO Meeting)",
    "CREATE REL TABLE IF NOT EXISTS WORKS_ON(FROM Person TO Project)",
    "CREATE REL TABLE IF NOT EXISTS TAGGED_WITH(FROM Document TO Topic)",
    "CREATE REL TABLE IF NOT EXISTS FOLLOWED_UP_BY(FROM ActionItem TO ActionItem)",
    "CREATE REL TABLE IF NOT EXISTS OWNS(FROM Person TO Project)",
    "CREATE REL TABLE IF NOT EXISTS BLOCKS(FROM ActionItem TO ActionItem)",
]

# Maps relationship type → (from_table, to_table)
_REL_TABLE_MAP: dict[str, tuple[str, str]] = {
    "ATTENDED": ("Person", "Meeting"),
    "MENTIONED_IN": ("Person", "Document"),
    "ASSIGNED_TO": ("ActionItem", "Person"),
    "RELATED_TO": ("Document", "Document"),
    "DECIDED_IN": ("Decision", "Meeting"),
    "WORKS_ON": ("Person", "Project"),
    "TAGGED_WITH": ("Document", "Topic"),
    "FOLLOWED_UP_BY": ("ActionItem", "ActionItem"),
    "OWNS": ("Person", "Project"),
    "BLOCKS": ("ActionItem", "ActionItem"),
}

# Set of valid node table names — used to allowlist the `table` parameter in
# methods that interpolate it into Cypher queries.
_NODE_TABLE_NAMES: frozenset[str] = frozenset(
    {"Person", "Project", "Topic", "Decision", "ActionItem", "Meeting", "Document"}
)

# Pattern for safe Cypher property key identifiers (letters, digits, underscore).
_SAFE_KEY_RE: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# ---------------------------------------------------------------------------
# GraphStore
# ---------------------------------------------------------------------------


class GraphStore:
    """Kuzu-backed graph database for entity and relationship storage."""

    _db: Any
    _conn: Any

    def __init__(self, db_path: Path) -> None:
        # Create the parent directory; Kuzu creates db_path itself as a directory
        db_path.parent.mkdir(parents=True, exist_ok=True)
        log = logger.bind(db_path=str(db_path))
        log.info("graph_store.init")
        self._db = kuzu.Database(str(db_path))
        self._conn = kuzu.Connection(self._db)
        self._init_schema()
        log.info("graph_store.ready")

    def _init_schema(self) -> None:
        log = logger.bind(node_tables=len(_NODE_DDL), rel_tables=len(_REL_DDL))
        log.info("graph_store.schema_init")
        for stmt in _NODE_DDL + _REL_DDL:
            self._conn.execute(stmt)
        log.info("graph_store.schema_ready")

    def execute(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a Cypher query and return rows as a list of dicts."""
        result = self._conn.execute(query, params or {})
        col_names: list[str] = result.get_column_names()
        rows: list[dict[str, Any]] = []
        while result.has_next():
            row: list[Any] = result.get_next()
            rows.append(dict(zip(col_names, row, strict=True)))
        return rows

    # --- Person ---

    def upsert_person(self, node: PersonNode) -> None:
        params: dict[str, Any] = {
            "id": node.id,
            "name": node.name,
            "email": node.email,
            "aliases": node.aliases,
            "first_seen": node.first_seen,
            "last_seen": node.last_seen,
        }
        self._conn.execute(
            "MERGE (n:Person {id: $id}) "
            "SET n.name = $name, n.email = $email, n.aliases = $aliases, "
            "n.first_seen = $first_seen, n.last_seen = $last_seen",
            params,
        )

    def get_person(self, node_id: str) -> PersonNode | None:
        rows = self.execute(
            "MATCH (n:Person {id: $id}) "
            "RETURN n.id, n.name, n.email, n.aliases, n.first_seen, n.last_seen",
            {"id": node_id},
        )
        if not rows:
            return None
        row = rows[0]
        return PersonNode(
            id=row["n.id"],
            name=row["n.name"],
            email=row["n.email"] or "",
            aliases=row["n.aliases"] or [],
            first_seen=row["n.first_seen"],
            last_seen=row["n.last_seen"],
        )

    # --- Project ---

    def upsert_project(self, node: ProjectNode) -> None:
        params: dict[str, Any] = {
            "id": node.id,
            "name": node.name,
            "description": node.description,
            "aliases": node.aliases,
        }
        self._conn.execute(
            "MERGE (n:Project {id: $id}) "
            "SET n.name = $name, n.description = $description, n.aliases = $aliases",
            params,
        )

    def get_project(self, node_id: str) -> ProjectNode | None:
        rows = self.execute(
            "MATCH (n:Project {id: $id}) RETURN n.id, n.name, n.description, n.aliases",
            {"id": node_id},
        )
        if not rows:
            return None
        row = rows[0]
        return ProjectNode(
            id=row["n.id"],
            name=row["n.name"],
            description=row["n.description"] or "",
            aliases=row["n.aliases"] or [],
        )

    # --- Topic ---

    def upsert_topic(self, node: TopicNode) -> None:
        params: dict[str, Any] = {
            "id": node.id,
            "name": node.name,
            "keywords": node.keywords,
        }
        self._conn.execute(
            "MERGE (n:Topic {id: $id}) SET n.name = $name, n.keywords = $keywords",
            params,
        )

    def get_topic(self, node_id: str) -> TopicNode | None:
        rows = self.execute(
            "MATCH (n:Topic {id: $id}) RETURN n.id, n.name, n.keywords",
            {"id": node_id},
        )
        if not rows:
            return None
        row = rows[0]
        return TopicNode(
            id=row["n.id"],
            name=row["n.name"],
            keywords=row["n.keywords"] or [],
        )

    # --- Decision ---

    def upsert_decision(self, node: DecisionNode) -> None:
        params: dict[str, Any] = {
            "id": node.id,
            "summary": node.summary,
            "made_at": node.made_at,
            "context": node.context,
        }
        self._conn.execute(
            "MERGE (n:Decision {id: $id}) "
            "SET n.summary = $summary, n.made_at = $made_at, n.context = $context",
            params,
        )

    def get_decision(self, node_id: str) -> DecisionNode | None:
        rows = self.execute(
            "MATCH (n:Decision {id: $id}) RETURN n.id, n.summary, n.made_at, n.context",
            {"id": node_id},
        )
        if not rows:
            return None
        row = rows[0]
        return DecisionNode(
            id=row["n.id"],
            summary=row["n.summary"],
            made_at=row["n.made_at"],
            context=row["n.context"] or "",
        )

    # --- ActionItem ---

    def upsert_action_item(self, node: ActionItemNode) -> None:
        params: dict[str, Any] = {
            "id": node.id,
            "description": node.description,
            "status": node.status,
            "due_date": node.due_date,
            "assignee_id": node.assignee_id,
        }
        self._conn.execute(
            "MERGE (n:ActionItem {id: $id}) "
            "SET n.description = $description, n.status = $status, "
            "n.due_date = $due_date, n.assignee_id = $assignee_id",
            params,
        )

    def get_action_item(self, node_id: str) -> ActionItemNode | None:
        rows = self.execute(
            "MATCH (n:ActionItem {id: $id}) "
            "RETURN n.id, n.description, n.status, n.due_date, n.assignee_id",
            {"id": node_id},
        )
        if not rows:
            return None
        row = rows[0]
        return ActionItemNode(
            id=row["n.id"],
            description=row["n.description"],
            status=row["n.status"] or "open",
            due_date=row["n.due_date"],
            assignee_id=row["n.assignee_id"] or "",
        )

    # --- Meeting ---

    def upsert_meeting(self, node: MeetingNode) -> None:
        params: dict[str, Any] = {
            "id": node.id,
            "title": node.title,
            "date": node.date,
            "duration_minutes": node.duration_minutes,
            "source_id": node.source_id,
        }
        self._conn.execute(
            "MERGE (n:Meeting {id: $id}) "
            "SET n.title = $title, n.date = $date, "
            "n.duration_minutes = $duration_minutes, n.source_id = $source_id",
            params,
        )

    def get_meeting(self, node_id: str) -> MeetingNode | None:
        rows = self.execute(
            "MATCH (n:Meeting {id: $id}) "
            "RETURN n.id, n.title, n.date, n.duration_minutes, n.source_id",
            {"id": node_id},
        )
        if not rows:
            return None
        row = rows[0]
        return MeetingNode(
            id=row["n.id"],
            title=row["n.title"],
            date=row["n.date"],
            duration_minutes=row["n.duration_minutes"] or 0,
            source_id=row["n.source_id"] or "",
        )

    # --- Document ---

    def upsert_document(self, node: DocumentNode) -> None:
        params: dict[str, Any] = {
            "id": node.id,
            "title": node.title,
            "source_type": node.source_type,
            "source_id": node.source_id,
            "created_at": node.created_at,
        }
        self._conn.execute(
            "MERGE (n:Document {id: $id}) "
            "SET n.title = $title, n.source_type = $source_type, "
            "n.source_id = $source_id, n.created_at = $created_at",
            params,
        )

    def get_document(self, node_id: str) -> DocumentNode | None:
        rows = self.execute(
            "MATCH (n:Document {id: $id}) "
            "RETURN n.id, n.title, n.source_type, n.source_id, n.created_at",
            {"id": node_id},
        )
        if not rows:
            return None
        row = rows[0]
        return DocumentNode(
            id=row["n.id"],
            title=row["n.title"],
            source_type=row["n.source_type"] or "",
            source_id=row["n.source_id"] or "",
            created_at=row["n.created_at"],
        )

    # --- Generic delete ---

    def delete_node(self, table: str, node_id: str) -> None:
        """Delete a node and all its relationships by table name and id.

        Raises ``ValueError`` if ``table`` is not a known node type.
        """
        if table not in _NODE_TABLE_NAMES:
            raise ValueError(
                f"Unknown node table: {table!r}. Must be one of {sorted(_NODE_TABLE_NAMES)}"
            )
        self._conn.execute(
            f"MATCH (n:{table} {{id: $id}}) DETACH DELETE n",
            {"id": node_id},
        )

    # --- Relationships ---

    def create_relationship(
        self,
        rel_type: str,
        from_table: str,
        from_id: str,
        to_table: str,
        to_id: str,
        props: dict[str, Any] | None = None,
    ) -> None:
        """Create or merge a relationship between two nodes.

        ``rel_type``, ``from_table``, and ``to_table`` are validated against
        the known schema before being interpolated into the Cypher query.
        Property keys in ``props`` must be valid Cypher identifiers.

        Raises ``ValueError`` for unknown or invalid arguments.
        """
        if rel_type not in _REL_TABLE_MAP:
            raise ValueError(f"Unknown relationship type: {rel_type!r}")
        expected_from, expected_to = _REL_TABLE_MAP[rel_type]
        if from_table != expected_from:
            raise ValueError(f"{rel_type} expects FROM {expected_from}, got {from_table!r}")
        if to_table != expected_to:
            raise ValueError(f"{rel_type} expects TO {expected_to}, got {to_table!r}")
        params: dict[str, Any] = {"from_id": from_id, "to_id": to_id}
        if props:
            for key in props:
                if not _SAFE_KEY_RE.match(key):
                    raise ValueError(f"Invalid property key: {key!r}")
            set_items = ", ".join(f"r.{k} = ${k}" for k in props)
            set_clause = f" SET {set_items}"
            params.update(props)
        else:
            set_clause = ""
        query = (
            f"MATCH (a:{from_table} {{id: $from_id}}), (b:{to_table} {{id: $to_id}}) "
            f"MERGE (a)-[r:{rel_type}]->(b){set_clause}"
        )
        self._conn.execute(query, params)

    def get_relationships(
        self,
        rel_type: str,
        from_id: str | None = None,
        to_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return relationships of the given type, optionally filtered by endpoint ids.

        Returns a list of dicts with keys ``from_id`` and ``to_id``.
        Raises ``ValueError`` for unknown relationship types.
        """
        if rel_type not in _REL_TABLE_MAP:
            raise ValueError(f"Unknown relationship type: {rel_type!r}")
        from_table, to_table = _REL_TABLE_MAP[rel_type]
        where_parts: list[str] = []
        params: dict[str, Any] = {}
        if from_id is not None:
            where_parts.append("a.id = $from_id")
            params["from_id"] = from_id
        if to_id is not None:
            where_parts.append("b.id = $to_id")
            params["to_id"] = to_id
        where_clause = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
        query = (
            f"MATCH (a:{from_table})-[r:{rel_type}]->(b:{to_table}){where_clause} "
            "RETURN a.id AS from_id, b.id AS to_id"
        )
        return self.execute(query, params)

    def close(self) -> None:
        del self._conn
        del self._db
