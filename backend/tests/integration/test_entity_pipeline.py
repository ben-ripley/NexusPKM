"""Integration tests for EntityExtractionPipeline.

Tests the full pipeline: document → LLM → entities → Kuzu graph (tmp_path).
Spec: F-006 FR-2
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nexuspkm.engine.contradiction import ContradictionDetector
from nexuspkm.engine.deduplication import EntityDeduplicator
from nexuspkm.engine.entity_pipeline import EntityExtractionPipeline
from nexuspkm.engine.extraction import EntityExtractor
from nexuspkm.engine.graph_store import GraphStore
from nexuspkm.models.document import Document, DocumentMetadata, SourceType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_document(
    doc_id: str = "doc-pipe-1", content: str = "Alice owns Project Alpha."
) -> Document:
    now = datetime.now(tz=UTC)
    meta = DocumentMetadata(
        source_type=SourceType.OBSIDIAN_NOTE,
        source_id=doc_id,
        title="Pipeline Test",
        created_at=now,
        updated_at=now,
        synced_at=now,
    )
    return Document(id=doc_id, content=content, metadata=meta)


def _extraction_payload(entities: list[dict], relationships: list[dict]) -> str:
    return json.dumps({"entities": entities, "relationships": relationships, "confidence": 0.9})


# ---------------------------------------------------------------------------
# Full pipeline — entities stored in Kuzu
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_stores_person_in_graph(tmp_path: Path) -> None:
    graph_store = GraphStore(tmp_path / "kuzu")
    graph_lock = threading.Lock()

    provider = MagicMock()
    provider.generate = AsyncMock(
        return_value=MagicMock(
            content=_extraction_payload(
                entities=[
                    {
                        "type": "person",
                        "name": "Alice",
                        "properties": {"email": "alice@example.com"},
                        "confidence": 0.9,
                        "source_span": "Alice",
                    }
                ],
                relationships=[],
            )
        )
    )

    extractor = EntityExtractor(provider)
    deduplicator = EntityDeduplicator(graph_store, graph_lock)
    contradiction_detector = ContradictionDetector(tmp_path / "contradictions.db")
    await contradiction_detector.init()
    pipeline = EntityExtractionPipeline(
        extractor,
        deduplicator,
        graph_store,
        graph_lock,
        contradiction_detector,
    )

    doc = _make_document()
    await pipeline.process(doc)

    # Verify entity was written to Kuzu
    rows = graph_store.execute("MATCH (n:Person) RETURN n.id, n.name, n.email")
    assert len(rows) == 1
    assert rows[0]["n.name"] == "Alice"
    assert rows[0]["n.email"] == "alice@example.com"

    graph_store.close()


@pytest.mark.asyncio
async def test_pipeline_stores_project_in_graph(tmp_path: Path) -> None:
    graph_store = GraphStore(tmp_path / "kuzu")
    graph_lock = threading.Lock()

    provider = MagicMock()
    provider.generate = AsyncMock(
        return_value=MagicMock(
            content=_extraction_payload(
                entities=[
                    {
                        "type": "project",
                        "name": "Project Alpha",
                        "properties": {"description": "Main project"},
                        "confidence": 0.85,
                        "source_span": "Project Alpha",
                    }
                ],
                relationships=[],
            )
        )
    )

    extractor = EntityExtractor(provider)
    deduplicator = EntityDeduplicator(graph_store, graph_lock)
    contradiction_detector = ContradictionDetector(tmp_path / "contradictions.db")
    await contradiction_detector.init()
    pipeline = EntityExtractionPipeline(
        extractor,
        deduplicator,
        graph_store,
        graph_lock,
        contradiction_detector,
    )

    await pipeline.process(_make_document())

    rows = graph_store.execute("MATCH (n:Project) RETURN n.name")
    assert len(rows) == 1
    assert rows[0]["n.name"] == "Project Alpha"

    graph_store.close()


@pytest.mark.asyncio
async def test_pipeline_deduplicates_existing_entity(tmp_path: Path) -> None:
    """Second process call for same person should not create a duplicate."""
    graph_store = GraphStore(tmp_path / "kuzu")
    graph_lock = threading.Lock()

    person_payload = _extraction_payload(
        entities=[
            {
                "type": "person",
                "name": "Bob Smith",
                "properties": {"email": "bob@example.com"},
                "confidence": 0.9,
                "source_span": "Bob Smith",
            }
        ],
        relationships=[],
    )
    provider = MagicMock()
    provider.generate = AsyncMock(return_value=MagicMock(content=person_payload))

    extractor = EntityExtractor(provider)
    deduplicator = EntityDeduplicator(graph_store, graph_lock)
    contradiction_detector = ContradictionDetector(tmp_path / "contradictions.db")
    await contradiction_detector.init()
    pipeline = EntityExtractionPipeline(
        extractor, deduplicator, graph_store, graph_lock, contradiction_detector
    )

    await pipeline.process(_make_document("doc-1"))
    await pipeline.process(_make_document("doc-2"))

    rows = graph_store.execute("MATCH (n:Person {name: 'Bob Smith'}) RETURN n.id")
    assert len(rows) == 1  # exactly one, not two

    graph_store.close()


@pytest.mark.asyncio
async def test_pipeline_detects_contradiction(tmp_path: Path) -> None:
    """Status conflict between two documents should be detected."""
    graph_store = GraphStore(tmp_path / "kuzu")
    graph_lock = threading.Lock()

    # First document: action item is open
    payload1 = _extraction_payload(
        entities=[
            {
                "type": "action_item",
                "name": "Finish report",
                "properties": {"status": "open"},
                "confidence": 0.9,
                "source_span": "Finish report",
            }
        ],
        relationships=[],
    )
    # Second document: same action item is done (status conflict)
    payload2 = _extraction_payload(
        entities=[
            {
                "type": "action_item",
                "name": "Finish report",
                "properties": {"status": "done"},
                "confidence": 0.9,
                "source_span": "Finish report",
            }
        ],
        relationships=[],
    )

    provider = MagicMock()
    provider.generate = AsyncMock(
        side_effect=[
            MagicMock(content=payload1),
            MagicMock(content=payload2),
        ]
    )

    extractor = EntityExtractor(provider)
    deduplicator = EntityDeduplicator(graph_store, graph_lock)
    contradiction_detector = ContradictionDetector(tmp_path / "contradictions.db")
    await contradiction_detector.init()
    pipeline = EntityExtractionPipeline(
        extractor, deduplicator, graph_store, graph_lock, contradiction_detector
    )

    await pipeline.process(_make_document("doc-c1"))
    await pipeline.process(_make_document("doc-c2"))

    unresolved = await contradiction_detector.list_unresolved()
    assert len(unresolved) >= 1
    assert any(c.field_name == "status" for c in unresolved)

    graph_store.close()


@pytest.mark.asyncio
async def test_pipeline_handles_empty_extraction(tmp_path: Path) -> None:
    """Pipeline with no extracted entities should complete without error."""
    graph_store = GraphStore(tmp_path / "kuzu")
    graph_lock = threading.Lock()

    provider = MagicMock()
    provider.generate = AsyncMock(
        return_value=MagicMock(content=_extraction_payload(entities=[], relationships=[]))
    )

    extractor = EntityExtractor(provider)
    deduplicator = EntityDeduplicator(graph_store, graph_lock)
    contradiction_detector = ContradictionDetector(tmp_path / "contradictions.db")
    await contradiction_detector.init()
    pipeline = EntityExtractionPipeline(
        extractor, deduplicator, graph_store, graph_lock, contradiction_detector
    )

    # Should not raise
    await pipeline.process(_make_document())

    rows = graph_store.execute("MATCH (n:Person) RETURN count(n) AS cnt")
    assert rows[0]["cnt"] == 0

    graph_store.close()
