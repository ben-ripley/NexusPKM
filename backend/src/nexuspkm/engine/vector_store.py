"""LanceDB vector store implementation.

Provides VectorStore — the single access point for all vector storage and
similarity search operations in NexusPKM.

Spec: F-002 FR-3
"""

from __future__ import annotations

import asyncio
import datetime
from typing import Any, Self

import pyarrow as pa
import structlog
from pydantic import BaseModel, ConfigDict, model_validator

from nexuspkm.models.document import ChunkResult, SourceType

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Public models
# ---------------------------------------------------------------------------

TABLE_NAME = "documents"


def _escape_sql_string(value: str) -> str:
    """Escape a string value for safe interpolation in a SQL filter expression.

    Replaces each single quote with two single quotes (standard SQL escaping).
    LanceDB's where() only accepts plain strings — parameterised queries are
    not supported by the API — so this is the correct mitigation.
    """
    return value.replace("'", "''")


def _dt_to_sql(dt: datetime.datetime) -> str:
    """Format a datetime as a DuckDB TIMESTAMP literal string (microsecond precision).

    Normalises to UTC so the literal is always unambiguous regardless of the
    input timezone.
    """
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.UTC).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")


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
    url: str | None = None


class SearchFilters(BaseModel):
    """Optional filters applied to vector search queries.

    date_from / date_to bound the ``created_at`` timestamp of stored chunks.
    When both are supplied, date_from must not be later than date_to.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_type: SourceType | None = None
    date_from: datetime.datetime | None = None
    date_to: datetime.datetime | None = None

    @model_validator(mode="after")
    def date_range_is_valid(self) -> Self:
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("date_from must not be later than date_to")
        return self


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
        self._open_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _open(self) -> None:
        """Connect to (or create) the LanceDB database and open the table.

        Protected by an asyncio.Lock so concurrent callers cannot race to
        create the table simultaneously.
        """
        async with self._open_lock:
            # Re-check inside the lock in case another coroutine opened it
            # while we were waiting.
            if self._table is not None:
                return

            if self._conn is None:
                import lancedb

                self._conn = await lancedb.connect_async(self._db_path)

            schema = self._build_schema()
            list_response = await self._conn.list_tables()
            # lancedb ≥0.14 returns a ListTablesResponse object; extract the
            # plain list before using `in` to avoid false negatives.
            existing: list[str] = (
                list_response.tables
                if hasattr(list_response, "tables")
                else list(list_response)
            )
            if TABLE_NAME in existing:
                self._table = await self._conn.open_table(TABLE_NAME)
                # Schema migration: add url column if the table predates it.
                # Pass a pa.field so the stored type (utf8) matches _build_schema
                # exactly — the SQL-expression dict form maps VARCHAR to large_utf8
                # which causes merge_insert to reject incoming utf8 data.
                current_schema = await self._table.schema()
                if "url" not in current_schema.names:
                    await self._table.add_columns(pa.field("url", pa.string()))
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

        Optionally filters by source_type and/or date range (created_at).
        Score is computed as ``1.0 - cosine_distance`` where cosine_distance
        is in [0, 2] for unit vectors, giving scores in [-1, 1] (negative
        values are clamped to 0 by the retriever's combined-score formula).
        """
        if top_k <= 0:
            raise ValueError(f"top_k must be a positive integer, got {top_k}")

        if self._table is None:
            await self._open()

        query = self._table.vector_search(vector).distance_type("cosine")

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
                pa.field("created_at", pa.timestamp("us", tz="UTC")),
                pa.field("updated_at", pa.timestamp("us", tz="UTC")),
                pa.field("url", pa.string()),
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
                "created_at": pa.array(
                    [c.created_at for c in chunks], type=pa.timestamp("us", tz="UTC")
                ),
                "updated_at": pa.array(
                    [c.updated_at for c in chunks], type=pa.timestamp("us", tz="UTC")
                ),
                "url": [c.url for c in chunks],
            }
        )

    @staticmethod
    def _build_where(filters: SearchFilters | None) -> str:
        if filters is None:
            return ""

        clauses: list[str] = []

        if filters.source_type is not None:
            # Apply escaping defensively even though SourceType is a validated
            # enum — guards against future enum values with unexpected characters.
            safe_type = _escape_sql_string(filters.source_type.value)
            clauses.append(f"source_type = '{safe_type}'")

        if filters.date_from is not None and filters.date_to is not None:
            clauses.append(
                f"created_at >= TIMESTAMP '{_dt_to_sql(filters.date_from)}'"
                f" AND created_at <= TIMESTAMP '{_dt_to_sql(filters.date_to)}'"
            )
        elif filters.date_from is not None:
            clauses.append(f"created_at >= TIMESTAMP '{_dt_to_sql(filters.date_from)}'")
        elif filters.date_to is not None:
            clauses.append(f"created_at <= TIMESTAMP '{_dt_to_sql(filters.date_to)}'")

        return " AND ".join(clauses)

    @staticmethod
    def _arrow_to_chunk_results(table: pa.Table) -> list[ChunkResult]:
        if table.num_rows == 0:
            return []

        if "_distance" not in table.column_names:
            raise ValueError(
                "LanceDB search result is missing expected '_distance' column; "
                f"got columns: {table.column_names}"
            )

        rows = table.to_pydict()
        results: list[ChunkResult] = []
        for i in range(table.num_rows):
            distance = float(rows["_distance"][i])
            score = 1.0 - distance
            created_at: datetime.datetime = rows["created_at"][i]
            # LanceDB returns timestamps with ZoneInfo; normalise to stdlib UTC.
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=datetime.UTC)
            else:
                created_at = created_at.astimezone(datetime.UTC)

            url_val = rows["url"][i] if "url" in rows else None
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
                    url=url_val if url_val else None,
                )
            )
        return results
