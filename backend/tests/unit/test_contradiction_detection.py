"""Unit tests for ContradictionDetector.

Tests: date conflict, status conflict, assignment conflict detection.
Spec: F-006 FR-5
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nexuspkm.engine.contradiction import ContradictionDetector
from nexuspkm.models.contradiction import ContradictionType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_contradictions.db"


@pytest.fixture
async def detector(db_path: Path) -> ContradictionDetector:
    det = ContradictionDetector(db_path)
    await det.init()
    return det


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detector_creates_table(db_path: Path) -> None:
    det = ContradictionDetector(db_path)
    await det.init()
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='contradictions'"
    )
    assert cursor.fetchone() is not None
    conn.close()


# ---------------------------------------------------------------------------
# Date conflict detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_date_conflict(detector: ContradictionDetector) -> None:
    contradictions = await detector.detect(
        entity_id="action-1",
        existing_properties={"due_date": "2026-03-15"},
        new_properties={"due_date": "2026-03-20"},
        source_doc_id="doc-1",
    )

    assert len(contradictions) == 1
    c = contradictions[0]
    assert c.entity_id == "action-1"
    assert c.field_name == "due_date"
    assert c.old_value == "2026-03-15"
    assert c.new_value == "2026-03-20"
    assert c.contradiction_type == ContradictionType.DATE_CONFLICT


@pytest.mark.asyncio
async def test_no_date_conflict_same_value(detector: ContradictionDetector) -> None:
    contradictions = await detector.detect(
        entity_id="action-2",
        existing_properties={"due_date": "2026-03-15"},
        new_properties={"due_date": "2026-03-15"},
        source_doc_id="doc-2",
    )

    assert contradictions == []


# ---------------------------------------------------------------------------
# Status conflict detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_status_conflict(detector: ContradictionDetector) -> None:
    contradictions = await detector.detect(
        entity_id="proj-1",
        existing_properties={"status": "in_progress"},
        new_properties={"status": "complete"},
        source_doc_id="doc-3",
    )

    assert len(contradictions) == 1
    c = contradictions[0]
    assert c.field_name == "status"
    assert c.contradiction_type == ContradictionType.STATUS_CONFLICT


@pytest.mark.asyncio
async def test_no_status_conflict_same_status(detector: ContradictionDetector) -> None:
    contradictions = await detector.detect(
        entity_id="proj-2",
        existing_properties={"status": "open"},
        new_properties={"status": "open"},
        source_doc_id="doc-4",
    )

    assert contradictions == []


# ---------------------------------------------------------------------------
# Assignment conflict detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_assignment_conflict(detector: ContradictionDetector) -> None:
    contradictions = await detector.detect(
        entity_id="action-3",
        existing_properties={"assignee_id": "alice"},
        new_properties={"assignee_id": "bob"},
        source_doc_id="doc-5",
    )

    assert len(contradictions) == 1
    c = contradictions[0]
    assert c.field_name == "assignee_id"
    assert c.contradiction_type == ContradictionType.ASSIGNMENT_CONFLICT


@pytest.mark.asyncio
async def test_no_conflict_unrelated_fields(detector: ContradictionDetector) -> None:
    contradictions = await detector.detect(
        entity_id="person-1",
        existing_properties={"name": "Alice"},
        new_properties={"name": "Alice Smith"},
        source_doc_id="doc-6",
    )

    assert contradictions == []


# ---------------------------------------------------------------------------
# Multiple conflicts in one call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_multiple_conflicts(detector: ContradictionDetector) -> None:
    contradictions = await detector.detect(
        entity_id="action-4",
        existing_properties={"due_date": "2026-01-01", "status": "open", "assignee_id": "alice"},
        new_properties={"due_date": "2026-02-01", "status": "done", "assignee_id": "bob"},
        source_doc_id="doc-7",
    )

    assert len(contradictions) == 3
    types = {c.contradiction_type for c in contradictions}
    assert ContradictionType.DATE_CONFLICT in types
    assert ContradictionType.STATUS_CONFLICT in types
    assert ContradictionType.ASSIGNMENT_CONFLICT in types


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_contradiction(detector: ContradictionDetector, db_path: Path) -> None:
    contradictions = await detector.detect(
        entity_id="entity-1",
        existing_properties={"status": "open"},
        new_properties={"status": "closed"},
        source_doc_id="doc-8",
    )
    await detector.persist(contradictions)

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT entity_id, field_name FROM contradictions").fetchall()
    conn.close()

    assert len(rows) == 1
    assert rows[0] == ("entity-1", "status")


@pytest.mark.asyncio
async def test_list_unresolved_contradictions(
    detector: ContradictionDetector,
) -> None:
    contradictions = await detector.detect(
        entity_id="entity-2",
        existing_properties={"status": "open"},
        new_properties={"status": "done"},
        source_doc_id="doc-9",
    )
    await detector.persist(contradictions)

    unresolved = await detector.list_unresolved()
    assert len(unresolved) == 1
    assert unresolved[0].entity_id == "entity-2"
    assert unresolved[0].resolved is False


@pytest.mark.asyncio
async def test_resolve_contradiction(
    detector: ContradictionDetector,
) -> None:
    contradictions = await detector.detect(
        entity_id="entity-3",
        existing_properties={"status": "open"},
        new_properties={"status": "done"},
        source_doc_id="doc-10",
    )
    await detector.persist(contradictions)

    c = contradictions[0]
    await detector.resolve(c.id)

    unresolved = await detector.list_unresolved()
    assert unresolved == []

    all_rows = await detector.list_all()
    assert len(all_rows) == 1
    assert all_rows[0].resolved is True
    assert all_rows[0].resolved_at is not None
