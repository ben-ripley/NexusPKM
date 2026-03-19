"""Unit tests for the Kuzu graph store.

Covers:
- Node model validation (pure Python)
- DDL list format and counts (pure Python)
- Schema init idempotency (embedded Kuzu via tmp_path)
- execute() row-to-dict mapping (embedded Kuzu via tmp_path)

Spec: F-002 FR-4
"""

from __future__ import annotations

import datetime
from pathlib import Path  # noqa: I001

import pytest
from pydantic import ValidationError

from nexuspkm.engine.graph_store import (
    _NODE_DDL,
    _REL_DDL,
    ActionItemNode,
    DecisionNode,
    DocumentNode,
    GraphStore,
    MeetingNode,
    PersonNode,
    ProjectNode,
    TopicNode,
)

# ---------------------------------------------------------------------------
# Node model validation
# ---------------------------------------------------------------------------


class TestPersonNode:
    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            PersonNode(id="p1")  # type: ignore[call-arg]  # missing name

    def test_defaults(self) -> None:
        p = PersonNode(id="p1", name="Alice")
        assert p.email == ""
        assert p.aliases == []
        assert p.first_seen is None
        assert p.last_seen is None

    def test_full_construction(self) -> None:
        now = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
        p = PersonNode(id="p1", name="Alice", email="a@x.com", aliases=["Al"], first_seen=now)
        assert p.email == "a@x.com"
        assert p.aliases == ["Al"]
        assert p.first_seen == now

    def test_aliases_independent_between_instances(self) -> None:
        p1 = PersonNode(id="p1", name="A")
        p2 = PersonNode(id="p2", name="B")
        p1.aliases.append("alias")
        assert p2.aliases == []


class TestProjectNode:
    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            ProjectNode(id="x")  # type: ignore[call-arg]  # missing name

    def test_defaults(self) -> None:
        p = ProjectNode(id="p1", name="MyProject")
        assert p.description == ""
        assert p.aliases == []


class TestTopicNode:
    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            TopicNode(id="t1")  # type: ignore[call-arg]  # missing name

    def test_defaults(self) -> None:
        t = TopicNode(id="t1", name="Python")
        assert t.keywords == []


class TestDecisionNode:
    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            DecisionNode(id="d1")  # type: ignore[call-arg]  # missing summary

    def test_defaults(self) -> None:
        d = DecisionNode(id="d1", summary="Use Kuzu")
        assert d.made_at is None
        assert d.context == ""


class TestActionItemNode:
    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            ActionItemNode(id="a1")  # type: ignore[call-arg]  # missing description

    def test_defaults(self) -> None:
        a = ActionItemNode(id="a1", description="Fix bug")
        assert a.status == "open"
        assert a.due_date is None
        assert a.assignee_id == ""


class TestMeetingNode:
    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            MeetingNode(id="m1")  # type: ignore[call-arg]  # missing title

    def test_defaults(self) -> None:
        m = MeetingNode(id="m1", title="Standup")
        assert m.date is None
        assert m.duration_minutes == 0
        assert m.source_id == ""


class TestDocumentNode:
    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            DocumentNode(id="doc1")  # type: ignore[call-arg]  # missing title

    def test_defaults(self) -> None:
        d = DocumentNode(id="doc1", title="Notes")
        assert d.source_type == ""
        assert d.source_id == ""
        assert d.created_at is None


# ---------------------------------------------------------------------------
# DDL list assertions
# ---------------------------------------------------------------------------


def test_node_ddl_count() -> None:
    assert len(_NODE_DDL) == 7


def test_rel_ddl_count() -> None:
    assert len(_REL_DDL) == 10


def test_all_node_ddl_use_if_not_exists() -> None:
    for stmt in _NODE_DDL:
        assert "IF NOT EXISTS" in stmt, f"Missing IF NOT EXISTS: {stmt}"


def test_all_rel_ddl_use_if_not_exists() -> None:
    for stmt in _REL_DDL:
        assert "IF NOT EXISTS" in stmt, f"Missing IF NOT EXISTS: {stmt}"


def test_node_ddl_covers_all_types() -> None:
    combined = " ".join(_NODE_DDL)
    for table in ("Person", "Project", "Topic", "Decision", "ActionItem", "Meeting", "Document"):
        assert table in combined, f"Node table {table} missing from DDL"


def test_rel_ddl_covers_all_types() -> None:
    combined = " ".join(_REL_DDL)
    for rel in (
        "ATTENDED",
        "MENTIONED_IN",
        "ASSIGNED_TO",
        "RELATED_TO",
        "DECIDED_IN",
        "WORKS_ON",
        "TAGGED_WITH",
        "FOLLOWED_UP_BY",
        "OWNS",
        "BLOCKS",
    ):
        assert rel in combined, f"Relationship {rel} missing from DDL"


# ---------------------------------------------------------------------------
# Schema init (uses embedded Kuzu, fast)
# ---------------------------------------------------------------------------


def test_schema_init_idempotent(tmp_path: Path) -> None:
    """Calling _init_schema() twice does not raise."""
    gs = GraphStore(tmp_path / "kuzu")
    gs._init_schema()  # call a second time
    gs.close()


def test_graph_store_creates_parent_dir(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "kuzu"
    gs = GraphStore(db_path)
    assert db_path.parent.exists()
    gs.close()


# ---------------------------------------------------------------------------
# execute() row-to-dict mapping
# ---------------------------------------------------------------------------


def test_execute_returns_list_of_dicts(tmp_path: Path) -> None:
    gs = GraphStore(tmp_path / "kuzu")
    gs.upsert_person(PersonNode(id="p1", name="Alice"))
    rows = gs.execute("MATCH (n:Person) RETURN n.id, n.name")
    assert len(rows) == 1
    assert rows[0]["n.id"] == "p1"
    assert rows[0]["n.name"] == "Alice"
    gs.close()


def test_execute_no_results(tmp_path: Path) -> None:
    gs = GraphStore(tmp_path / "kuzu")
    rows = gs.execute("MATCH (n:Person {id: $id}) RETURN n.id", {"id": "missing"})
    assert rows == []
    gs.close()


def test_execute_multiple_rows(tmp_path: Path) -> None:
    gs = GraphStore(tmp_path / "kuzu")
    gs.upsert_person(PersonNode(id="p1", name="Alice"))
    gs.upsert_person(PersonNode(id="p2", name="Bob"))
    rows = gs.execute("MATCH (n:Person) RETURN n.id ORDER BY n.id")
    assert len(rows) == 2
    assert rows[0]["n.id"] == "p1"
    assert rows[1]["n.id"] == "p2"
    gs.close()


# ---------------------------------------------------------------------------
# Allowlist validation
# ---------------------------------------------------------------------------


def test_delete_node_unknown_table_raises(tmp_path: Path) -> None:
    gs = GraphStore(tmp_path / "kuzu")
    with pytest.raises(ValueError, match="Unknown node table"):
        gs.delete_node("NonExistent", "id1")
    gs.close()


def test_create_relationship_unknown_rel_type_raises(tmp_path: Path) -> None:
    gs = GraphStore(tmp_path / "kuzu")
    with pytest.raises(ValueError, match="Unknown relationship type"):
        gs.create_relationship("UNKNOWN_REL", "Person", "p1", "Meeting", "m1")
    gs.close()


def test_create_relationship_wrong_from_table_raises(tmp_path: Path) -> None:
    gs = GraphStore(tmp_path / "kuzu")
    with pytest.raises(ValueError, match="expects FROM"):
        gs.create_relationship("ATTENDED", "Document", "d1", "Meeting", "m1")
    gs.close()


def test_create_relationship_invalid_prop_key_raises(tmp_path: Path) -> None:
    gs = GraphStore(tmp_path / "kuzu")
    gs.upsert_person(PersonNode(id="p1", name="Alice"))
    gs.upsert_meeting(MeetingNode(id="m1", title="Standup"))
    with pytest.raises(ValueError, match="Invalid property key"):
        gs.create_relationship(
            "ATTENDED",
            "Person",
            "p1",
            "Meeting",
            "m1",
            props={"bad key!": "value"},
        )
    gs.close()


def test_get_relationships_unknown_rel_type_raises(tmp_path: Path) -> None:
    gs = GraphStore(tmp_path / "kuzu")
    with pytest.raises(ValueError, match="Unknown relationship type"):
        gs.get_relationships("UNKNOWN_REL")
    gs.close()
