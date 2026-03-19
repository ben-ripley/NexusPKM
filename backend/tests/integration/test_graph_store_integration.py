"""Integration tests for the Kuzu graph store.

Uses a real Kuzu database in tmp_path for each test. Covers:
- Full CRUD for each node type
- Update via re-upsert (MERGE idempotency)
- Delete
- Relationship creation and retrieval
- Multi-hop Cypher query via execute()
- Persistence across close/reopen

Spec: F-002 FR-4
"""

from __future__ import annotations

import datetime
from collections.abc import Generator
from pathlib import Path

import pytest

from nexuspkm.engine.graph_store import (
    ActionItemNode,
    DecisionNode,
    DocumentNode,
    GraphStore,
    MeetingNode,
    PersonNode,
    ProjectNode,
    TopicNode,
)


@pytest.fixture
def gs(tmp_path: Path) -> Generator[GraphStore, None, None]:
    store = GraphStore(tmp_path / "kuzu")
    yield store
    store.close()


@pytest.fixture
def gs_path(tmp_path: Path) -> Path:
    """Returns the db path for the persistence test (which manages its own lifecycle)."""
    return tmp_path / "kuzu"


# ---------------------------------------------------------------------------
# Person CRUD
# ---------------------------------------------------------------------------


def test_person_upsert_and_get(gs: GraphStore) -> None:
    p = PersonNode(id="p1", name="Alice", email="alice@example.com", aliases=["Al"])
    gs.upsert_person(p)
    result = gs.get_person("p1")
    assert result is not None
    assert result.id == "p1"
    assert result.name == "Alice"
    assert result.email == "alice@example.com"
    assert result.aliases == ["Al"]


def test_person_get_missing(gs: GraphStore) -> None:
    assert gs.get_person("missing") is None


def test_person_update_via_upsert(gs: GraphStore) -> None:
    gs.upsert_person(PersonNode(id="p1", name="Alice"))
    gs.upsert_person(PersonNode(id="p1", name="Alice Updated", email="new@example.com"))
    result = gs.get_person("p1")
    assert result is not None
    assert result.name == "Alice Updated"
    assert result.email == "new@example.com"


def test_person_with_timestamps(gs: GraphStore) -> None:
    now = datetime.datetime(2026, 1, 15, 10, 30, 0, tzinfo=datetime.UTC)
    gs.upsert_person(PersonNode(id="p1", name="Alice", first_seen=now, last_seen=now))
    result = gs.get_person("p1")
    assert result is not None
    assert result.first_seen is not None
    assert result.last_seen is not None


def test_person_delete(gs: GraphStore) -> None:
    gs.upsert_person(PersonNode(id="p1", name="Alice"))
    gs.delete_node("Person", "p1")
    assert gs.get_person("p1") is None


def test_person_delete_nonexistent_is_noop(gs: GraphStore) -> None:
    gs.delete_node("Person", "does_not_exist")


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------


def test_project_upsert_and_get(gs: GraphStore) -> None:
    p = ProjectNode(id="proj1", name="NexusPKM", description="PKM app", aliases=["NX"])
    gs.upsert_project(p)
    result = gs.get_project("proj1")
    assert result is not None
    assert result.name == "NexusPKM"
    assert result.description == "PKM app"
    assert result.aliases == ["NX"]


def test_project_get_missing(gs: GraphStore) -> None:
    assert gs.get_project("missing") is None


def test_project_update_via_upsert(gs: GraphStore) -> None:
    gs.upsert_project(ProjectNode(id="p1", name="Old Name"))
    gs.upsert_project(ProjectNode(id="p1", name="New Name", description="Updated"))
    result = gs.get_project("p1")
    assert result is not None
    assert result.name == "New Name"
    assert result.description == "Updated"


def test_project_delete(gs: GraphStore) -> None:
    gs.upsert_project(ProjectNode(id="p1", name="MyProject"))
    gs.delete_node("Project", "p1")
    assert gs.get_project("p1") is None


# ---------------------------------------------------------------------------
# Topic CRUD
# ---------------------------------------------------------------------------


def test_topic_upsert_and_get(gs: GraphStore) -> None:
    t = TopicNode(id="t1", name="Python", keywords=["python", "programming"])
    gs.upsert_topic(t)
    result = gs.get_topic("t1")
    assert result is not None
    assert result.name == "Python"
    assert result.keywords == ["python", "programming"]


def test_topic_get_missing(gs: GraphStore) -> None:
    assert gs.get_topic("missing") is None


def test_topic_delete(gs: GraphStore) -> None:
    gs.upsert_topic(TopicNode(id="t1", name="AI"))
    gs.delete_node("Topic", "t1")
    assert gs.get_topic("t1") is None


# ---------------------------------------------------------------------------
# Decision CRUD
# ---------------------------------------------------------------------------


def test_decision_upsert_and_get(gs: GraphStore) -> None:
    now = datetime.datetime(2026, 3, 1, tzinfo=datetime.UTC)
    d = DecisionNode(id="d1", summary="Use Kuzu", made_at=now, context="Graph DB selection")
    gs.upsert_decision(d)
    result = gs.get_decision("d1")
    assert result is not None
    assert result.summary == "Use Kuzu"
    assert result.context == "Graph DB selection"
    assert result.made_at is not None


def test_decision_get_missing(gs: GraphStore) -> None:
    assert gs.get_decision("missing") is None


def test_decision_delete(gs: GraphStore) -> None:
    gs.upsert_decision(DecisionNode(id="d1", summary="Adopt TDD"))
    gs.delete_node("Decision", "d1")
    assert gs.get_decision("d1") is None


# ---------------------------------------------------------------------------
# ActionItem CRUD
# ---------------------------------------------------------------------------


def test_action_item_upsert_and_get(gs: GraphStore) -> None:
    due = datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC)
    a = ActionItemNode(
        id="a1", description="Fix bug", status="open", due_date=due, assignee_id="p1"
    )
    gs.upsert_action_item(a)
    result = gs.get_action_item("a1")
    assert result is not None
    assert result.description == "Fix bug"
    assert result.status == "open"
    assert result.assignee_id == "p1"
    assert result.due_date is not None


def test_action_item_get_missing(gs: GraphStore) -> None:
    assert gs.get_action_item("missing") is None


def test_action_item_update_status(gs: GraphStore) -> None:
    gs.upsert_action_item(ActionItemNode(id="a1", description="Task", status="open"))
    gs.upsert_action_item(ActionItemNode(id="a1", description="Task", status="done"))
    result = gs.get_action_item("a1")
    assert result is not None
    assert result.status == "done"


def test_action_item_delete(gs: GraphStore) -> None:
    gs.upsert_action_item(ActionItemNode(id="a1", description="Task"))
    gs.delete_node("ActionItem", "a1")
    assert gs.get_action_item("a1") is None


# ---------------------------------------------------------------------------
# Meeting CRUD
# ---------------------------------------------------------------------------


def test_meeting_upsert_and_get(gs: GraphStore) -> None:
    date = datetime.datetime(2026, 3, 19, 9, 0, tzinfo=datetime.UTC)
    m = MeetingNode(id="m1", title="Standup", date=date, duration_minutes=30, source_id="teams:123")
    gs.upsert_meeting(m)
    result = gs.get_meeting("m1")
    assert result is not None
    assert result.title == "Standup"
    assert result.duration_minutes == 30
    assert result.source_id == "teams:123"
    assert result.date is not None


def test_meeting_get_missing(gs: GraphStore) -> None:
    assert gs.get_meeting("missing") is None


def test_meeting_delete(gs: GraphStore) -> None:
    gs.upsert_meeting(MeetingNode(id="m1", title="Sprint Review"))
    gs.delete_node("Meeting", "m1")
    assert gs.get_meeting("m1") is None


# ---------------------------------------------------------------------------
# Document CRUD
# ---------------------------------------------------------------------------


def test_document_upsert_and_get(gs: GraphStore) -> None:
    created = datetime.datetime(2026, 2, 1, tzinfo=datetime.UTC)
    d = DocumentNode(
        id="doc1",
        title="Design Notes",
        source_type="obsidian_note",
        source_id="obs:abc",
        created_at=created,
    )
    gs.upsert_document(d)
    result = gs.get_document("doc1")
    assert result is not None
    assert result.title == "Design Notes"
    assert result.source_type == "obsidian_note"
    assert result.source_id == "obs:abc"
    assert result.created_at is not None


def test_document_get_missing(gs: GraphStore) -> None:
    assert gs.get_document("missing") is None


def test_document_delete(gs: GraphStore) -> None:
    gs.upsert_document(DocumentNode(id="doc1", title="Notes"))
    gs.delete_node("Document", "doc1")
    assert gs.get_document("doc1") is None


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------


def test_person_attended_meeting(gs: GraphStore) -> None:
    gs.upsert_person(PersonNode(id="p1", name="Alice"))
    gs.upsert_meeting(MeetingNode(id="m1", title="Standup"))
    gs.create_relationship("ATTENDED", "Person", "p1", "Meeting", "m1")
    rels = gs.get_relationships("ATTENDED", from_id="p1")
    assert len(rels) == 1
    assert rels[0]["from_id"] == "p1"
    assert rels[0]["to_id"] == "m1"


def test_get_relationships_by_to_id(gs: GraphStore) -> None:
    gs.upsert_person(PersonNode(id="p1", name="Alice"))
    gs.upsert_person(PersonNode(id="p2", name="Bob"))
    gs.upsert_meeting(MeetingNode(id="m1", title="Standup"))
    gs.create_relationship("ATTENDED", "Person", "p1", "Meeting", "m1")
    gs.create_relationship("ATTENDED", "Person", "p2", "Meeting", "m1")
    rels = gs.get_relationships("ATTENDED", to_id="m1")
    assert len(rels) == 2
    attendee_ids = {r["from_id"] for r in rels}
    assert attendee_ids == {"p1", "p2"}


def test_get_relationships_no_filter(gs: GraphStore) -> None:
    gs.upsert_person(PersonNode(id="p1", name="Alice"))
    gs.upsert_meeting(MeetingNode(id="m1", title="Standup"))
    gs.upsert_meeting(MeetingNode(id="m2", title="Retro"))
    gs.create_relationship("ATTENDED", "Person", "p1", "Meeting", "m1")
    gs.create_relationship("ATTENDED", "Person", "p1", "Meeting", "m2")
    rels = gs.get_relationships("ATTENDED")
    assert len(rels) == 2


def test_relationship_with_props(gs: GraphStore) -> None:
    gs.upsert_person(PersonNode(id="p1", name="Alice"))
    gs.upsert_document(DocumentNode(id="doc1", title="Notes"))
    gs.create_relationship(
        "MENTIONED_IN",
        "Person",
        "p1",
        "Document",
        "doc1",
        props={"context": "discussed in section 2"},
    )
    rels = gs.get_relationships("MENTIONED_IN", from_id="p1")
    assert len(rels) == 1
    assert rels[0]["from_id"] == "p1"
    assert rels[0]["to_id"] == "doc1"
    # Verify the property is actually persisted on the relationship edge
    rows = gs.execute(
        "MATCH (a:Person {id: $pid})-[r:MENTIONED_IN]->(b:Document) RETURN r.context AS ctx",
        {"pid": "p1"},
    )
    assert len(rows) == 1
    assert rows[0]["ctx"] == "discussed in section 2"


def test_relationship_merge_idempotent(gs: GraphStore) -> None:
    gs.upsert_person(PersonNode(id="p1", name="Alice"))
    gs.upsert_meeting(MeetingNode(id="m1", title="Standup"))
    gs.create_relationship("ATTENDED", "Person", "p1", "Meeting", "m1")
    gs.create_relationship("ATTENDED", "Person", "p1", "Meeting", "m1")  # same again
    rels = gs.get_relationships("ATTENDED", from_id="p1")
    assert len(rels) == 1


def test_delete_removes_relationships(gs: GraphStore) -> None:
    """DETACH DELETE should remove the node and its relationships."""
    gs.upsert_person(PersonNode(id="p1", name="Alice"))
    gs.upsert_meeting(MeetingNode(id="m1", title="Standup"))
    gs.create_relationship("ATTENDED", "Person", "p1", "Meeting", "m1")
    gs.delete_node("Person", "p1")
    rels = gs.get_relationships("ATTENDED", from_id="p1")
    assert len(rels) == 0


# ---------------------------------------------------------------------------
# Multi-hop graph traversal via execute()
# ---------------------------------------------------------------------------


def test_multi_hop_person_to_document_via_meeting(gs: GraphStore) -> None:
    """Person ATTENDED Meeting; Document DECIDED_IN Meeting via Decision."""
    gs.upsert_person(PersonNode(id="p1", name="Alice"))
    gs.upsert_meeting(MeetingNode(id="m1", title="Sprint Planning"))
    gs.upsert_decision(DecisionNode(id="d1", summary="Use Python"))
    gs.create_relationship("ATTENDED", "Person", "p1", "Meeting", "m1")
    gs.create_relationship("DECIDED_IN", "Decision", "d1", "Meeting", "m1")

    # Find all decisions made in meetings that Alice attended
    rows = gs.execute(
        "MATCH (p:Person {id: $pid})-[:ATTENDED]->(m:Meeting)<-[:DECIDED_IN]-(d:Decision) "
        "RETURN d.id AS decision_id, d.summary AS summary",
        {"pid": "p1"},
    )
    assert len(rows) == 1
    assert rows[0]["decision_id"] == "d1"
    assert rows[0]["summary"] == "Use Python"


# ---------------------------------------------------------------------------
# Persistence across close/reopen
# ---------------------------------------------------------------------------


def test_persistence_across_close_reopen(gs_path: Path) -> None:
    gs1 = GraphStore(gs_path)
    gs1.upsert_person(PersonNode(id="p1", name="Alice", email="alice@example.com"))
    gs1.upsert_meeting(MeetingNode(id="m1", title="Standup"))
    gs1.create_relationship("ATTENDED", "Person", "p1", "Meeting", "m1")
    gs1.close()

    gs2 = GraphStore(gs_path)
    person = gs2.get_person("p1")
    assert person is not None
    assert person.name == "Alice"
    assert person.email == "alice@example.com"

    rels = gs2.get_relationships("ATTENDED", from_id="p1")
    assert len(rels) == 1
    assert rels[0]["to_id"] == "m1"
    gs2.close()
