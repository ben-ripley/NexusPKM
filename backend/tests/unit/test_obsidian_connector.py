"""Unit tests for ObsidianNotesConnector.

Covers: connectors/obsidian/connector.py
Spec: F-004
NXP-49, NXP-58
"""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path

from nexuspkm.config.models import ObsidianConnectorConfig
from nexuspkm.connectors.obsidian.connector import ObsidianNotesConnector, _ObsidianFileEntry
from nexuspkm.models.document import SourceType, SyncState


def _make_connector(tmp_path: Path, *, vault_path: Path | None = None) -> ObsidianNotesConnector:
    vault = vault_path or tmp_path / "vault"
    vault.mkdir(exist_ok=True)
    config = ObsidianConnectorConfig(
        enabled=True,
        vault_path=vault,
        sync_interval_minutes=5,
    )
    return ObsidianNotesConnector(
        vault_path=vault,
        state_dir=tmp_path / "state",
        config=config,
    )


# ---------------------------------------------------------------------------
# _is_excluded
# ---------------------------------------------------------------------------


def test_is_excluded_obsidian_dir(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    assert connector._is_excluded(".obsidian/config.json") is True


def test_is_excluded_trash_dir(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    assert connector._is_excluded(".trash/deleted-note.md") is True


def test_is_excluded_templates_dir(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    assert connector._is_excluded("templates/daily.md") is True


def test_is_excluded_nested_pattern(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    assert connector._is_excluded("folder/.obsidian/workspace") is True


def test_is_excluded_regular_note(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    assert connector._is_excluded("notes/my-note.md") is False


def test_is_excluded_top_level_note(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    assert connector._is_excluded("my-note.md") is False


# ---------------------------------------------------------------------------
# _to_document
# ---------------------------------------------------------------------------


def test_to_document_fields(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "My Note.md"
    note.write_text("---\ntitle: Custom Title\n---\nBody content here.")
    connector = _make_connector(tmp_path, vault_path=vault)
    doc = connector._to_document(note)

    assert doc.metadata.source_type == SourceType.OBSIDIAN_NOTE
    assert doc.content  # non-empty
    assert len(doc.id) > 0


def test_to_document_uses_frontmatter_title(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "filename.md"
    note.write_text("---\ntitle: Frontmatter Title\n---\nContent.")
    connector = _make_connector(tmp_path, vault_path=vault)
    doc = connector._to_document(note)
    assert doc.metadata.title == "Frontmatter Title"


def test_to_document_falls_back_to_filename_stem(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "My Great Note.md"
    note.write_text("Just a body, no frontmatter.")
    connector = _make_connector(tmp_path, vault_path=vault)
    doc = connector._to_document(note)
    assert doc.metadata.title == "My Great Note"


def test_to_document_uuid_is_deterministic(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "stable.md"
    note.write_text("Content.")
    connector = _make_connector(tmp_path, vault_path=vault)
    doc1 = connector._to_document(note)
    doc2 = connector._to_document(note)
    assert doc1.id == doc2.id


def test_to_document_uuid_uses_namespace_oid(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "note.md"
    note.write_text("Content.")
    connector = _make_connector(tmp_path, vault_path=vault)
    doc = connector._to_document(note)
    rel = note.relative_to(vault)
    expected_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"obsidian:{rel}"))
    assert doc.id == expected_id


def test_to_document_tags_in_metadata(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "tagged.md"
    note.write_text("---\ntags: [project, work]\n---\nContent.")
    connector = _make_connector(tmp_path, vault_path=vault)
    doc = connector._to_document(note)
    assert "project" in doc.metadata.tags
    assert "work" in doc.metadata.tags


def test_to_document_wikilinks_in_custom(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "linked.md"
    note.write_text("See [[Other Note]] for details.")
    connector = _make_connector(tmp_path, vault_path=vault)
    doc = connector._to_document(note)
    assert "Other Note" in doc.metadata.custom.get("wikilinks", [])


def test_to_document_source_type(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "note.md"
    note.write_text("Content.")
    connector = _make_connector(tmp_path, vault_path=vault)
    doc = connector._to_document(note)
    assert doc.metadata.source_type == SourceType.OBSIDIAN_NOTE


# ---------------------------------------------------------------------------
# authenticate
# ---------------------------------------------------------------------------


async def test_authenticate_vault_exists(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    result = await connector.authenticate()
    assert result is True


async def test_authenticate_vault_missing(tmp_path: Path) -> None:
    vault = tmp_path / "nonexistent-vault"
    config = ObsidianConnectorConfig(enabled=True, vault_path=vault)
    connector = ObsidianNotesConnector(
        vault_path=vault,
        state_dir=tmp_path / "state",
        config=config,
    )
    result = await connector.authenticate()
    assert result is False


# ---------------------------------------------------------------------------
# get_sync_state / restore_sync_state
# ---------------------------------------------------------------------------


async def test_get_sync_state_missing_file(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    state = await connector.get_sync_state()
    assert state.last_synced_at is None
    assert state.cursor is None


async def test_restore_and_get_sync_state_roundtrip(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    now = datetime.datetime.now(tz=datetime.UTC)
    state_in = SyncState(last_synced_at=now, cursor="abc")
    await connector.restore_sync_state(state_in)
    state_out = await connector.get_sync_state()
    assert state_out.cursor == "abc"
    # Timestamps may differ by microseconds due to JSON serialisation
    assert state_out.last_synced_at is not None
    assert abs((state_out.last_synced_at - now).total_seconds()) < 1


# ---------------------------------------------------------------------------
# _load_file_state / _save_file_state
# ---------------------------------------------------------------------------


async def test_load_file_state_missing(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    state = await connector._load_file_state()
    assert state == {}


async def test_save_and_load_file_state_roundtrip(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    entry: _ObsidianFileEntry = {
        "doc_id": "some-uuid",
        "mtime": 1234567890.123,
        "content_hash": "abc123",
    }
    state = {"notes/my-note.md": entry}
    await connector._save_file_state(state)
    loaded = await connector._load_file_state()
    assert loaded == state


# ---------------------------------------------------------------------------
# fetch_deleted_ids
# ---------------------------------------------------------------------------


async def test_fetch_deleted_ids_returns_doc_ids_for_removed_files(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "deleted.md"
    note.write_text("Content.")
    connector = _make_connector(tmp_path, vault_path=vault)

    # Seed file state as if note was previously indexed
    entry: _ObsidianFileEntry = {
        "doc_id": "dead-beef-uuid",
        "mtime": 111.0,
        "content_hash": "hash1",
    }
    await connector._save_file_state({"deleted.md": entry})

    # Now remove the file
    note.unlink()

    deleted_ids = await connector.fetch_deleted_ids()
    assert "dead-beef-uuid" in deleted_ids


async def test_fetch_deleted_ids_no_deletions(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "present.md"
    note.write_text("Content.")
    connector = _make_connector(tmp_path, vault_path=vault)

    entry: _ObsidianFileEntry = {
        "doc_id": "present-uuid",
        "mtime": 111.0,
        "content_hash": "hash1",
    }
    await connector._save_file_state({"present.md": entry})

    deleted_ids = await connector.fetch_deleted_ids()
    assert deleted_ids == []


async def test_fetch_deleted_ids_empty_state(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    deleted_ids = await connector.fetch_deleted_ids()
    assert deleted_ids == []
