"""Unit tests for AppleNotesConnector.

Covers: connectors/apple_notes/connector.py
Spec: F-009
NXP-68
"""

from __future__ import annotations

import datetime
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from nexuspkm.config.models import AppleNotesConnectorConfig
from nexuspkm.connectors.apple_notes.connector import AppleNotesConnector, _AppleNoteEntry
from nexuspkm.models.document import SourceType


@pytest.fixture(autouse=True)
def _patch_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate macOS for all tests in this module.

    Individual tests that need to test non-macOS behaviour override this with
    ``patch("sys.platform", "linux")`` inside their body.
    """
    monkeypatch.setattr(sys, "platform", "darwin")


def _make_connector(tmp_path: Path, **kwargs: object) -> AppleNotesConnector:
    config = AppleNotesConnectorConfig(enabled=True, **kwargs)  # type: ignore[arg-type]
    return AppleNotesConnector(state_dir=tmp_path / "state", config=config)


def _make_note(
    note_id: str = "note-1",
    name: str = "My Note",
    body: str = "<p>Content</p>",
    folder: str = "Notes",
    created: str = "2026-01-01T00:00:00.000Z",
    modified: str = "2026-01-01T00:00:00.000Z",
) -> dict[str, str]:
    return {
        "id": note_id,
        "name": name,
        "body": body,
        "folder": folder,
        "created": created,
        "modified": modified,
    }


# ---------------------------------------------------------------------------
# Platform guard
# ---------------------------------------------------------------------------


async def test_platform_check_non_macos(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    with patch("sys.platform", "linux"):
        result = await connector.authenticate()
    assert result is False


async def test_platform_check_macos(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    with patch("sys.platform", "darwin"):
        result = await connector.authenticate()
    assert result is True


# ---------------------------------------------------------------------------
# _parse_applescript_output
# ---------------------------------------------------------------------------


def test_parse_applescript_output(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    notes = [
        {
            "id": "x-coredata://UUID/ICNote/p1",
            "name": "Test Note",
            "body": "<html><body><p>Hello</p></body></html>",
            "folder": "Notes",
            "created": "2026-01-01T12:00:00.000Z",
            "modified": "2026-01-15T10:00:00.000Z",
        }
    ]
    sample_json = json.dumps(notes)
    result = connector._parse_applescript_output(sample_json)
    assert len(result) == 1
    assert result[0]["id"] == "x-coredata://UUID/ICNote/p1"
    assert result[0]["name"] == "Test Note"


def test_parse_applescript_output_empty(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    result = connector._parse_applescript_output("")
    assert result == []


def test_parse_applescript_output_invalid_json(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    result = connector._parse_applescript_output("not json {{}}")
    assert result == []


def test_parse_applescript_output_non_list(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    result = connector._parse_applescript_output('{"id": "1"}')
    assert result == []


def test_parse_applescript_output_multiple_notes(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    notes = [_make_note("n1"), _make_note("n2"), _make_note("n3")]
    result = connector._parse_applescript_output(json.dumps(notes))
    assert len(result) == 3


# ---------------------------------------------------------------------------
# Incremental sync: new note
# ---------------------------------------------------------------------------


async def test_incremental_sync_detects_new_note(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    note = _make_note("note-1")
    with patch.object(connector, "_fetch_notes", new=AsyncMock(return_value=[note])):
        docs = [doc async for doc in connector.fetch()]
    assert len(docs) == 1
    assert docs[0].metadata.source_type == SourceType.APPLE_NOTE


async def test_incremental_sync_yields_multiple_new_notes(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    notes = [_make_note("n1"), _make_note("n2"), _make_note("n3")]
    with patch.object(connector, "_fetch_notes", new=AsyncMock(return_value=notes)):
        docs = [doc async for doc in connector.fetch()]
    assert len(docs) == 3


# ---------------------------------------------------------------------------
# Incremental sync: skip unchanged
# ---------------------------------------------------------------------------


async def test_incremental_sync_skips_unchanged_note(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    note = _make_note("note-1", modified="2026-01-01T00:00:00.000Z")
    doc_id = str(uuid.uuid5(uuid.NAMESPACE_OID, "apple_note:note-1"))

    # Seed state: note-1 with same modified date
    state: dict[str, _AppleNoteEntry] = {
        "note-1": _AppleNoteEntry(doc_id=doc_id, modified="2026-01-01T00:00:00.000Z")
    }
    await connector._save_note_state(state)

    with patch.object(connector, "_fetch_notes", new=AsyncMock(return_value=[note])):
        docs = [doc async for doc in connector.fetch()]

    assert docs == []


async def test_incremental_sync_returns_updated_note(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    old_modified = "2026-01-01T00:00:00.000Z"
    new_modified = "2026-01-15T00:00:00.000Z"
    note = _make_note("note-1", modified=new_modified)
    doc_id = str(uuid.uuid5(uuid.NAMESPACE_OID, "apple_note:note-1"))

    # Seed state with old modified
    state: dict[str, _AppleNoteEntry] = {
        "note-1": _AppleNoteEntry(doc_id=doc_id, modified=old_modified)
    }
    await connector._save_note_state(state)

    with patch.object(connector, "_fetch_notes", new=AsyncMock(return_value=[note])):
        docs = [doc async for doc in connector.fetch()]

    assert len(docs) == 1
    assert docs[0].id == doc_id


# ---------------------------------------------------------------------------
# Deletion detection
# ---------------------------------------------------------------------------


async def test_incremental_sync_detects_deleted_note(tmp_path: Path) -> None:
    """Note in state but absent from current fetch → returned by fetch_deleted_ids."""
    connector = _make_connector(tmp_path)

    # Seed state with two notes
    state: dict[str, _AppleNoteEntry] = {
        "note-1": _AppleNoteEntry(doc_id="uuid-1", modified="2026-01-01T00:00:00.000Z"),
        "note-2": _AppleNoteEntry(doc_id="uuid-2", modified="2026-01-01T00:00:00.000Z"),
    }
    await connector._save_note_state(state)

    # Only note-2 exists now
    remaining = [_make_note("note-2")]
    with patch.object(connector, "_fetch_notes", new=AsyncMock(return_value=remaining)):
        deleted_ids = await connector.fetch_deleted_ids()

    assert "uuid-1" in deleted_ids
    assert "uuid-2" not in deleted_ids


async def test_fetch_deleted_ids_empty_state(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    with patch.object(connector, "_fetch_notes", new=AsyncMock(return_value=[])):
        deleted_ids = await connector.fetch_deleted_ids()
    assert deleted_ids == []


async def test_fetch_deleted_ids_no_deletions(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    note = _make_note("note-1")
    state: dict[str, _AppleNoteEntry] = {
        "note-1": _AppleNoteEntry(doc_id="uuid-1", modified="2026-01-01T00:00:00.000Z"),
    }
    await connector._save_note_state(state)

    with patch.object(connector, "_fetch_notes", new=AsyncMock(return_value=[note])):
        deleted_ids = await connector.fetch_deleted_ids()

    assert deleted_ids == []


async def test_fetch_deleted_ids_removes_stale_state(tmp_path: Path) -> None:
    """After fetch_deleted_ids, deleted entries must not reappear on next call."""
    connector = _make_connector(tmp_path)
    state: dict[str, _AppleNoteEntry] = {
        "gone": _AppleNoteEntry(doc_id="uuid-gone", modified="2026-01-01T00:00:00.000Z"),
    }
    await connector._save_note_state(state)

    with patch.object(connector, "_fetch_notes", new=AsyncMock(return_value=[])):
        first = await connector.fetch_deleted_ids()
    assert "uuid-gone" in first

    with patch.object(connector, "_fetch_notes", new=AsyncMock(return_value=[])):
        second = await connector.fetch_deleted_ids()
    assert second == []


# ---------------------------------------------------------------------------
# Document metadata
# ---------------------------------------------------------------------------


def test_document_metadata(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    note: dict[str, str] = {
        "id": "x-coredata://UUID/ICNote/p42",
        "name": "Meeting Notes",
        "body": "<p>Discussion points</p>",
        "folder": "Work",
        "created": "2026-01-01T00:00:00.000Z",
        "modified": "2026-01-15T00:00:00.000Z",
    }
    doc = connector._to_document(note)

    assert doc.metadata.source_type == SourceType.APPLE_NOTE
    assert doc.metadata.title == "Meeting Notes"
    assert doc.metadata.source_id == "x-coredata://UUID/ICNote/p42"
    assert doc.metadata.custom["folder"] == "Work"
    assert doc.metadata.custom["extraction_method"] == "applescript"


def test_document_id_is_deterministic(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    note = _make_note("note-stable")
    doc1 = connector._to_document(note)
    doc2 = connector._to_document(note)
    assert doc1.id == doc2.id


def test_document_id_uses_uuid5(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    note = _make_note("note-abc")
    doc = connector._to_document(note)
    expected = str(uuid.uuid5(uuid.NAMESPACE_OID, "apple_note:note-abc"))
    assert doc.id == expected


def test_document_content_falls_back_to_title_on_empty_body(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    note = _make_note("note-1", name="My Note Title", body="")
    doc = connector._to_document(note)
    assert doc.content  # non-empty
    assert len(doc.content) >= 1


def test_document_has_checklists_metadata(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    note = _make_note("n1", body='<ul><li data-checked="false">Task</li></ul>')
    doc = connector._to_document(note)
    assert doc.metadata.custom["has_checklists"] is True


def test_document_no_checklists_metadata(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    note = _make_note("n1", body="<p>Plain note</p>")
    doc = connector._to_document(note)
    assert doc.metadata.custom["has_checklists"] is False


def test_document_has_images_metadata(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    note = _make_note("n1", body='<p>See <img src="photo.jpg" /> above</p>')
    doc = connector._to_document(note)
    assert doc.metadata.custom["has_images"] is True


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


async def test_health_check_unavailable_non_macos(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    with patch("sys.platform", "linux"):
        status = await connector.health_check()
    assert status.status == "unavailable"
    assert status.last_error is not None
    assert "macOS" in status.last_error


async def test_health_check_healthy_on_macos(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    with patch("sys.platform", "darwin"):
        status = await connector.health_check()
    assert status.status in ("healthy", "degraded")


# ---------------------------------------------------------------------------
# get_sync_state / restore_sync_state
# ---------------------------------------------------------------------------


async def test_get_sync_state_missing_file(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    state = await connector.get_sync_state()
    assert state.last_synced_at is None
    assert state.cursor is None


async def test_restore_and_get_sync_state_roundtrip(tmp_path: Path) -> None:
    from nexuspkm.models.document import SyncState

    connector = _make_connector(tmp_path)
    now = datetime.datetime.now(tz=datetime.UTC)
    state_in = SyncState(last_synced_at=now, cursor="checkpoint-42")
    await connector.restore_sync_state(state_in)
    state_out = await connector.get_sync_state()
    assert state_out.cursor == "checkpoint-42"
    assert state_out.last_synced_at is not None
    assert abs((state_out.last_synced_at - now).total_seconds()) < 1


# ---------------------------------------------------------------------------
# update_sync_interval
# ---------------------------------------------------------------------------


def test_update_sync_interval(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    connector.update_sync_interval(30)
    assert connector._config.sync_interval_minutes == 30


def test_update_sync_interval_preserves_extraction_method(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path, extraction_method="sqlite")
    connector.update_sync_interval(20)
    assert connector._config.extraction_method == "sqlite"


# ---------------------------------------------------------------------------
# _load_note_state / _save_note_state
# ---------------------------------------------------------------------------


async def test_load_note_state_missing(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    state = await connector._load_note_state()
    assert state == {}


async def test_save_and_load_note_state_roundtrip(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    entry = _AppleNoteEntry(doc_id="some-uuid", modified="2026-01-01T00:00:00.000Z")
    await connector._save_note_state({"note-1": entry})
    loaded = await connector._load_note_state()
    assert loaded["note-1"]["doc_id"] == "some-uuid"
    assert loaded["note-1"]["modified"] == "2026-01-01T00:00:00.000Z"


async def test_save_note_state_is_atomic(tmp_path: Path) -> None:
    """No .tmp file should remain after a successful save."""
    connector = _make_connector(tmp_path)
    entry = _AppleNoteEntry(doc_id="x", modified="2026-01-01T00:00:00.000Z")
    await connector._save_note_state({"n1": entry})
    tmp_file = connector._note_state_file.with_suffix(".tmp")
    assert not tmp_file.exists()
    assert connector._note_state_file.exists()
