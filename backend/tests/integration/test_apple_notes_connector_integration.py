"""Integration tests for AppleNotesConnector.

Tests full sync flow with mocked osascript subprocess output.
Spec: F-009
NXP-68
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from nexuspkm.config.models import AppleNotesConnectorConfig
from nexuspkm.connectors.apple_notes.connector import AppleNotesConnector
from nexuspkm.models.document import SourceType

_PATCH_SUBPROCESS = "nexuspkm.connectors.apple_notes.connector.subprocess.run"


def _make_connector(tmp_path: Path, **kwargs: object) -> AppleNotesConnector:
    config = AppleNotesConnectorConfig(enabled=True, **kwargs)  # type: ignore[arg-type]
    return AppleNotesConnector(state_dir=tmp_path / "state", config=config)


def _make_note(
    note_id: str,
    name: str = "Note",
    modified: str = "2026-01-01T00:00:00.000Z",
    created: str = "2026-01-01T00:00:00.000Z",
    folder: str = "Notes",
    body: str = "<p>Content</p>",
) -> dict[str, str]:
    return {
        "id": note_id,
        "name": name,
        "body": body,
        "folder": folder,
        "created": created,
        "modified": modified,
    }


def _mock_subprocess(notes: list[dict[str, str]], returncode: int = 0) -> MagicMock:
    """Build a MagicMock for subprocess.run returning the given notes as JSON."""
    mock_result = MagicMock()
    mock_result.returncode = returncode
    mock_result.stdout = json.dumps(notes)
    mock_result.stderr = ""
    return mock_result


# ---------------------------------------------------------------------------
# Full sync flow
# ---------------------------------------------------------------------------


async def test_full_sync_with_mocked_applescript(tmp_path: Path) -> None:
    """Full sync yields one Document per note returned by osascript."""
    notes = [
        _make_note("n1", name="Note 1"),
        _make_note("n2", name="Note 2"),
        _make_note("n3", name="Note 3"),
    ]
    mock_result = _mock_subprocess(notes)
    connector = _make_connector(tmp_path)

    with patch(_PATCH_SUBPROCESS, return_value=mock_result):
        docs = [doc async for doc in connector.fetch()]

    assert len(docs) == 3
    assert all(doc.metadata.source_type == SourceType.APPLE_NOTE for doc in docs)
    titles = {doc.metadata.title for doc in docs}
    assert titles == {"Note 1", "Note 2", "Note 3"}


async def test_full_sync_persists_state(tmp_path: Path) -> None:
    """After a full sync, note state is persisted to disk."""
    notes = [_make_note("n1"), _make_note("n2")]
    mock_result = _mock_subprocess(notes)
    connector = _make_connector(tmp_path)

    with patch(_PATCH_SUBPROCESS, return_value=mock_result):
        _ = [doc async for doc in connector.fetch()]

    state = await connector._load_note_state()
    assert "n1" in state
    assert "n2" in state


async def test_second_sync_skips_unchanged_notes(tmp_path: Path) -> None:
    """Second sync with no changes yields no documents."""
    notes = [_make_note("n1"), _make_note("n2")]
    mock_result = _mock_subprocess(notes)
    connector = _make_connector(tmp_path)

    with patch(_PATCH_SUBPROCESS, return_value=mock_result):
        first_docs = [doc async for doc in connector.fetch()]
    assert len(first_docs) == 2

    with patch(_PATCH_SUBPROCESS, return_value=mock_result):
        second_docs = [doc async for doc in connector.fetch()]
    assert second_docs == []


async def test_second_sync_yields_only_modified_note(tmp_path: Path) -> None:
    """Second sync only yields the note whose modification date changed."""
    notes_v1 = [
        _make_note("n1", modified="2026-01-01T00:00:00.000Z"),
        _make_note("n2", modified="2026-01-01T00:00:00.000Z"),
    ]
    notes_v2 = [
        _make_note("n1", modified="2026-01-01T00:00:00.000Z"),
        _make_note("n2", modified="2026-02-01T00:00:00.000Z"),  # n2 modified
    ]

    connector = _make_connector(tmp_path)

    with patch(_PATCH_SUBPROCESS, return_value=_mock_subprocess(notes_v1)):
        _ = [doc async for doc in connector.fetch()]

    with patch(_PATCH_SUBPROCESS, return_value=_mock_subprocess(notes_v2)):
        second_docs = [doc async for doc in connector.fetch()]

    assert len(second_docs) == 1
    assert second_docs[0].metadata.source_id == "n2"


# ---------------------------------------------------------------------------
# Deletion detection across two syncs
# ---------------------------------------------------------------------------


async def test_deletion_detection_across_two_syncs(tmp_path: Path) -> None:
    """Notes present in state but absent from current fetch are detected as deleted."""
    notes_v1 = [_make_note("n1"), _make_note("n2"), _make_note("n3")]
    notes_v2 = [_make_note("n1")]  # n2 and n3 deleted

    connector = _make_connector(tmp_path)

    # First sync: establish state for 3 notes
    with patch(_PATCH_SUBPROCESS, return_value=_mock_subprocess(notes_v1)):
        first_docs = [doc async for doc in connector.fetch()]
    assert len(first_docs) == 3

    # Second sync: fetch_deleted_ids detects 2 deletions
    with patch(_PATCH_SUBPROCESS, return_value=_mock_subprocess(notes_v2)):
        deleted_ids = await connector.fetch_deleted_ids()

    assert len(deleted_ids) == 2

    # The remaining note should still be in state
    state = await connector._load_note_state()
    assert "n1" in state
    assert "n2" not in state
    assert "n3" not in state


async def test_deletion_ids_are_stable_doc_ids(tmp_path: Path) -> None:
    """Deleted doc IDs match the IDs produced during initial sync."""
    import uuid as _uuid

    notes_all = [_make_note("n1"), _make_note("n2")]
    connector = _make_connector(tmp_path)

    with patch(_PATCH_SUBPROCESS, return_value=_mock_subprocess(notes_all)):
        initial_docs = [doc async for doc in connector.fetch()]

    n2_id = next(d.id for d in initial_docs if d.metadata.source_id == "n2")
    expected_id = str(_uuid.uuid5(_uuid.NAMESPACE_OID, "apple_note:n2"))
    assert n2_id == expected_id

    with patch(_PATCH_SUBPROCESS, return_value=_mock_subprocess([_make_note("n1")])):
        deleted_ids = await connector.fetch_deleted_ids()

    assert expected_id in deleted_ids


# ---------------------------------------------------------------------------
# osascript error handling
# ---------------------------------------------------------------------------


async def test_fetch_returns_empty_on_osascript_failure(tmp_path: Path) -> None:
    """If osascript exits non-zero, fetch yields nothing and records error."""
    error_result = MagicMock()
    error_result.returncode = 1
    error_result.stdout = ""
    error_result.stderr = "Notes is not running"

    connector = _make_connector(tmp_path)
    with patch(_PATCH_SUBPROCESS, return_value=error_result):
        docs = [doc async for doc in connector.fetch()]

    assert docs == []
    assert len(connector._last_sync_errors) > 0


async def test_health_check_degraded_after_error(tmp_path: Path) -> None:
    """health_check returns degraded when last sync had errors."""
    error_result = MagicMock()
    error_result.returncode = 1
    error_result.stdout = ""
    error_result.stderr = "error"

    connector = _make_connector(tmp_path)
    with patch(_PATCH_SUBPROCESS, return_value=error_result):
        _ = [doc async for doc in connector.fetch()]

    with patch("sys.platform", "darwin"):
        status = await connector.health_check()

    assert status.status == "degraded"


# ---------------------------------------------------------------------------
# Empty notes
# ---------------------------------------------------------------------------


async def test_sync_with_empty_note_list(tmp_path: Path) -> None:
    connector = _make_connector(tmp_path)
    with patch(_PATCH_SUBPROCESS, return_value=_mock_subprocess([])):
        docs = [doc async for doc in connector.fetch()]
    assert docs == []


# ---------------------------------------------------------------------------
# Document content and metadata
# ---------------------------------------------------------------------------


async def test_note_folder_in_custom_metadata(tmp_path: Path) -> None:
    notes = [_make_note("n1", name="Work Note", folder="Work Projects")]
    connector = _make_connector(tmp_path)
    with patch(_PATCH_SUBPROCESS, return_value=_mock_subprocess(notes)):
        docs = [doc async for doc in connector.fetch()]
    assert docs[0].metadata.custom["folder"] == "Work Projects"


async def test_html_body_converted_to_markdown(tmp_path: Path) -> None:
    notes = [_make_note("n1", body="<h1>Meeting</h1><p>Action items</p>")]
    connector = _make_connector(tmp_path)
    with patch(_PATCH_SUBPROCESS, return_value=_mock_subprocess(notes)):
        docs = [doc async for doc in connector.fetch()]
    assert "Meeting" in docs[0].content
    assert "Action items" in docs[0].content
