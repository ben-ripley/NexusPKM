"""LanceDB vector store implementation.

Provides VectorStore — the single access point for all vector storage and
similarity search operations in NexusPKM.

Spec: F-002 FR-3
"""

from __future__ import annotations

import datetime
from typing import Any

import pyarrow as pa
import structlog
from pydantic import BaseModel, ConfigDict

from nexuspkm.models.document import ChunkResult, SourceType

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Public models
# ---------------------------------------------------------------------------

TABLE_NAME = "documents"


def _escape_sql_string(value: str) -> str:
    """Escape a string value for safe interpolation in a SQL filter expression.

    Replaces each single quote with two single quotes (standard SQL escaping).
    """
    return value.replace("'", "''")


class VectorChunk(BaseModel):
    """A single chunk ready for storage in the vector store."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str
    document_id: str
    text: str
    vector: list[float]
    source_type: SourceType
    source_id: str
    title: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class SearchFilters(BaseModel):
    """Optional filters applied to vector search queries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_type: SourceType | None = None
    date_from: datetime.datetime | None = None
    date_to: datetime.datetime | None = None


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------


class VectorStore:
    """Async wrapper around a LanceDB `documents` table.

    Parameters
    ----------
    db_path:
        Filesystem path where LanceDB persists data (e.g. ``data/lancedb``).
    dimensions:
        Embedding vector length (must match the configured embedding provider).
    _conn:
        Injected connection for testing; when *None* a real connection is
        created lazily by ``_open()``.
    """

    def __init__(
        self,
        db_path: str,
        dimensions: int,
        *,
        _conn: Any = None,
    ) -> None:
        self._db_path = db_path
        self._dimensions = dimensions
        self._conn: Any = _conn
        self._table: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _open(self) -> None:
        """Connect to (or create) the LanceDB database and open the table."""
        if self._conn is None:
            import lancedb

            self._conn = await lancedb.connect_async(self._db_path)

        schema = self._build_schema()
        existing = await self._conn.list_tables()
        if TABLE_NAME in existing:
            self._table = await self._conn.open_table(TABLE_NAME)
        else:
            self._table = await self._conn.create_table(TABLE_NAME, schema=schema)

        logger.info("vector_store.opened", db_path=self._db_path, dimensions=self._dimensions)

    async def close(self) -> None:
        """Close the underlying database connection."""
        import inspect

        conn_close = getattr(self._conn, "close", None)
        if conn_close is not None:
            result = conn_close()
            if inspect.isawaitable(result):
                await result
        logger.info("vector_store.closed")

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def store(self, chunks: list[VectorChunk]) -> None:
        """Upsert *chunks* into the ``documents`` table.

        Uses ``merge_insert`` on ``chunk_id`` so re-processing the same
        document is idempotent.
        """
        if not chunks:
            return

        if self._table is None:
            await self._open()

        arrow_table = self._chunks_to_arrow(chunks)
        builder = self._table.merge_insert("chunk_id")
        builder.when_not_matched_insert_all()
        builder.when_matched_update_all()
        await builder.execute(arrow_table)
        logger.info("vector_store.stored", count=len(chunks))

    async def delete(self, document_id: str) -> None:
        """Delete all chunks belonging to *document_id*."""
        if self._table is None:
            await self._open()

        safe_id = _escape_sql_string(document_id)
        await self._table.delete(f"document_id = '{safe_id}'")
        logger.info("vector_store.deleted", document_id=document_id)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def search(
        self,
        vector: list[float],
        top_k: int = 10,
        filters: SearchFilters | None = None,
    ) -> list[ChunkResult]:
        """Return the *top_k* most similar chunks to *vector*.

        Optionally filters by source_type and/or date range.
        Score is computed as ``1.0 - cosine_distance``.
        """
        if self._table is None:
            await self._open()

        query = self._table.vector_search(vector)

        where_clause = self._build_where(filters)
        if where_clause:
            query = query.where(where_clause)

        query = query.limit(top_k)
        result = await query.to_arrow()

        return self._arrow_to_chunk_results(result)

    async def count(self) -> int:
        """Return total number of rows in the ``documents`` table."""
        if self._table is None:
            await self._open()

        return int(await self._table.count_rows())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_schema(self) -> pa.Schema:
        return pa.schema(
            [
                pa.field("chunk_id", pa.string()),
                pa.field("document_id", pa.string()),
                pa.field("text", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self._dimensions)),
                pa.field("source_type", pa.string()),
                pa.field("source_id", pa.string()),
                pa.field("title", pa.string()),
                pa.field("created_at", pa.string()),
                pa.field("updated_at", pa.string()),
            ]
        )

    @staticmethod
    def _chunks_to_arrow(chunks: list[VectorChunk]) -> pa.Table:
        return pa.table(
            {
                "chunk_id": [c.chunk_id for c in chunks],
                "document_id": [c.document_id for c in chunks],
                "text": [c.text for c in chunks],
                "vector": [c.vector for c in chunks],
                "source_type": [c.source_type.value for c in chunks],
                "source_id": [c.source_id for c in chunks],
                "title": [c.title for c in chunks],
                "created_at": [c.created_at.isoformat() for c in chunks],
                "updated_at": [c.updated_at.isoformat() for c in chunks],
            }
        )

    @staticmethod
    def _build_where(filters: SearchFilters | None) -> str:
        if filters is None:
            return ""

        clauses: list[str] = []

        if filters.source_type is not None:
            # SourceType is a validated enum — its .value contains only safe ASCII chars
            clauses.append(f"source_type = '{filters.source_type.value}'")

        if filters.date_from is not None and filters.date_to is not None:
            clauses.append(
                f"created_at >= '{filters.date_from.isoformat()}'"
                f" AND created_at <= '{filters.date_to.isoformat()}'"
            )
        elif filters.date_from is not None:
            clauses.append(f"created_at >= '{filters.date_from.isoformat()}'")
        elif filters.date_to is not None:
            clauses.append(f"created_at <= '{filters.date_to.isoformat()}'")

        return " AND ".join(clauses)

    @staticmethod
    def _arrow_to_chunk_results(table: pa.Table) -> list[ChunkResult]:
        if table.num_rows == 0:
            return []

        rows = table.to_pydict()
        results: list[ChunkResult] = []
        for i in range(table.num_rows):
            distance = float(rows["_distance"][i])
            score = 1.0 - distance
            created_at_raw = rows["created_at"][i]
            created_at = (
                datetime.datetime.fromisoformat(created_at_raw)
                if isinstance(created_at_raw, str)
                else created_at_raw
            )
            # Ensure timezone-aware
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=datetime.UTC)

            results.append(
                ChunkResult(
                    chunk_id=rows["chunk_id"][i],
                    document_id=rows["document_id"][i],
                    text=rows["text"][i],
                    score=score,
                    source_type=SourceType(rows["source_type"][i]),
                    source_id=rows["source_id"][i],
                    title=rows["title"][i],
                    created_at=created_at,
                )
            )
        return results
