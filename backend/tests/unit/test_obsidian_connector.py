"""Unit tests for ObsidianNotesConnector.

Covers: connectors/obsidian/connector.py
Spec: F-004
NXP-49, NXP-58
"""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

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


async def test_fetch_deleted_ids_file_exists_not_reported(tmp_path: Path) -> None:
    """A tracked file that still exists on disk is NOT reported as deleted,
    even if its extension no longer matches include_extensions."""
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "note.md"
    note.write_text("Content.")
    connector = _make_connector(tmp_path, vault_path=vault)

    entry: _ObsidianFileEntry = {
        "doc_id": "existing-uuid",
        "mtime": 111.0,
        "content_hash": "hash1",
    }
    await connector._save_file_state({"note.md": entry})

    # File still exists → should not be reported
    deleted_ids = await connector.fetch_deleted_ids()
    assert deleted_ids == []


async def test_fetch_deleted_ids_checks_actual_existence_not_extension_filter(
    tmp_path: Path,
) -> None:
    """fetch_deleted_ids uses actual file existence, not _collect_vault_paths,
    so a file tracked under a path that still exists is never a false positive."""
    vault = tmp_path / "vault"
    vault.mkdir()
    # Create a .txt file (not in include_extensions) and pretend it was tracked
    txt_note = vault / "legacy.txt"
    txt_note.write_text("old content")
    connector = _make_connector(tmp_path, vault_path=vault)

    entry: _ObsidianFileEntry = {
        "doc_id": "txt-uuid",
        "mtime": 1.0,
        "content_hash": "h",
    }
    await connector._save_file_state({"legacy.txt": entry})

    # File exists on disk → should NOT be reported as deleted regardless of extension
    deleted_ids = await connector.fetch_deleted_ids()
    assert "txt-uuid" not in deleted_ids


# ---------------------------------------------------------------------------
# Public properties
# ---------------------------------------------------------------------------


def test_vault_path_property(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    connector = _make_connector(tmp_path, vault_path=vault)
    assert connector.vault_path == vault


def test_watcher_running_false_initially(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    assert connector.watcher_running is False


# ---------------------------------------------------------------------------
# update_sync_interval
# ---------------------------------------------------------------------------


def test_update_sync_interval(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    connector.update_sync_interval(42)
    assert connector._config.sync_interval_minutes == 42


def test_update_sync_interval_preserves_other_fields(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    connector = _make_connector(tmp_path, vault_path=vault)
    original_vault = connector._config.vault_path
    original_patterns = connector._config.exclude_patterns
    connector.update_sync_interval(10)
    assert connector._config.vault_path == original_vault
    assert connector._config.exclude_patterns == original_patterns


# ---------------------------------------------------------------------------
# start_watching / stop_watching
# ---------------------------------------------------------------------------


async def test_start_watching_creates_task(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    on_upsert: AsyncMock = AsyncMock()
    on_delete: AsyncMock = AsyncMock()
    await connector.start_watching(on_upsert, on_delete)
    assert connector.watcher_running is True
    await connector.stop_watching()


async def test_start_watching_idempotent(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    on_upsert: AsyncMock = AsyncMock()
    on_delete: AsyncMock = AsyncMock()
    await connector.start_watching(on_upsert, on_delete)
    task1 = connector._watcher_task
    await connector.start_watching(on_upsert, on_delete)  # second call is no-op
    assert connector._watcher_task is task1
    await connector.stop_watching()


async def test_stop_watching_clears_task(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    on_upsert: AsyncMock = AsyncMock()
    on_delete: AsyncMock = AsyncMock()
    await connector.start_watching(on_upsert, on_delete)
    await connector.stop_watching()
    assert connector.watcher_running is False


async def test_stop_watching_noop_when_not_started(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    # Should not raise
    await connector.stop_watching()
    assert connector.watcher_running is False


async def test_watcher_crash_clears_watcher_running(tmp_path: Path) -> None:
    """If the watcher loop exits unexpectedly, watcher_running must return False."""
    import asyncio
    import sys
    from unittest.mock import MagicMock, patch

    connector = _make_connector(tmp_path)

    # Replace watchfiles in sys.modules so the local `import watchfiles` inside
    # _watch_loop picks up our mock regardless of whether the package is installed.
    async def _awatch_crash(*_args: object, **_kwargs: object):  # type: ignore[return]
        raise OSError("inotify limit exceeded")
        yield  # makes this an async generator so `async for` consumes it cleanly

    mock_wf = MagicMock()
    mock_wf.awatch = _awatch_crash

    with patch.dict(sys.modules, {"watchfiles": mock_wf}):
        connector._watcher_task = asyncio.create_task(
            connector._watch_loop(AsyncMock(), AsyncMock()),
            name="obsidian_watcher",
        )
        await asyncio.wait_for(connector._watcher_task, timeout=2.0)

    assert connector.watcher_running is False


# ---------------------------------------------------------------------------
# _handle_upsert / _handle_delete
# ---------------------------------------------------------------------------


async def test_handle_upsert_calls_on_upsert(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "test.md"
    note.write_text("Content.")
    connector = _make_connector(tmp_path, vault_path=vault)
    on_upsert: AsyncMock = AsyncMock()
    await connector._handle_upsert(note, on_upsert)
    on_upsert.assert_awaited_once()
    assert connector._total_docs_synced == 1


async def test_handle_upsert_does_not_raise_on_bad_file(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    missing = vault / "nonexistent.md"
    connector = _make_connector(tmp_path, vault_path=vault)
    on_upsert: AsyncMock = AsyncMock()
    # Should log a warning and not raise
    await connector._handle_upsert(missing, on_upsert)
    on_upsert.assert_not_awaited()


async def test_handle_delete_calls_on_delete_and_updates_state(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "to-delete.md"
    note.write_text("Content.")
    connector = _make_connector(tmp_path, vault_path=vault)

    entry: _ObsidianFileEntry = {"doc_id": "del-uuid", "mtime": 1.0, "content_hash": "h"}
    await connector._save_file_state({"to-delete.md": entry})

    on_delete: AsyncMock = AsyncMock()
    await connector._handle_delete(note, on_delete)

    on_delete.assert_awaited_once_with("del-uuid")
    remaining = await connector._load_file_state()
    assert "to-delete.md" not in remaining


async def test_handle_delete_noop_when_not_in_state(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "unknown.md"
    connector = _make_connector(tmp_path, vault_path=vault)
    on_delete: AsyncMock = AsyncMock()
    await connector._handle_delete(note, on_delete)
    on_delete.assert_not_awaited()


# ---------------------------------------------------------------------------
# _save_file_state atomic write
# ---------------------------------------------------------------------------


async def test_save_file_state_is_atomic(tmp_path: Path) -> None:
    """No .tmp file should remain after a successful save."""
    connector = _make_connector(tmp_path)
    entry: _ObsidianFileEntry = {"doc_id": "x", "mtime": 1.0, "content_hash": "h"}
    await connector._save_file_state({"note.md": entry})
    tmp_file = connector._file_state_file.with_suffix(".tmp")
    assert not tmp_file.exists()
    assert connector._file_state_file.exists()


# ---------------------------------------------------------------------------
# fetch_deleted_ids removes stale state
# ---------------------------------------------------------------------------


async def test_fetch_deleted_ids_removes_stale_entries_from_state(tmp_path: Path) -> None:
    """After fetch_deleted_ids, stale entries must not reappear on next call."""
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "vanishing.md"
    note.write_text("Content.")
    connector = _make_connector(tmp_path, vault_path=vault)

    entry: _ObsidianFileEntry = {"doc_id": "gone-uuid", "mtime": 1.0, "content_hash": "h"}
    await connector._save_file_state({"vanishing.md": entry})
    note.unlink()

    first_call = await connector.fetch_deleted_ids()
    assert "gone-uuid" in first_call

    second_call = await connector.fetch_deleted_ids()
    assert second_call == []
