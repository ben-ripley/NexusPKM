"""Integration tests for ObsidianNotesConnector.

Uses a real temporary vault directory with actual markdown files.
Spec: F-004
NXP-49
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from nexuspkm.config.models import ObsidianConnectorConfig
from nexuspkm.connectors.obsidian.connector import ObsidianNotesConnector
from nexuspkm.models.document import SourceType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_connector(vault: Path, tmp_path: Path) -> ObsidianNotesConnector:
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


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Create a temp vault with diverse markdown files."""
    v = tmp_path / "vault"
    v.mkdir()

    # Regular notes with frontmatter
    (v / "note-1.md").write_text(
        "---\ntitle: Note One\ntags: [work, alpha]\n---\n"
        "# Note One\n\nSee [[note-2]] and [[note-3|third note]].\n\n#productivity"
    )
    (v / "note-2.md").write_text(
        "---\ntitle: Note Two\n---\n\nLinked from note one.\n\n![[image.png]]"
    )
    (v / "note-3.md").write_text("No frontmatter here. Just plain content with #tag.")
    (v / "note-4.md").write_text(
        "---\nauthor: Alice\n---\n\n> [!NOTE] Important\n> Pay attention.\n"
    )
    (v / "note-5.md").write_text("Empty frontmatter test:\n\n---\n---\n\nBody text.")
    (v / "note-6.md").write_text("## Heading\n\nParagraph with [[wikilink]] here.")
    (v / "note-7.md").write_text("No special syntax, just prose.")

    # Subdirectory
    subdir = v / "projects"
    subdir.mkdir()
    (subdir / "alpha.md").write_text("---\ntitle: Alpha Project\n---\nProject alpha notes.")
    (subdir / "beta.md").write_text("Beta project notes.")

    # Edge cases
    (v / "empty-body.md").write_text("---\ntitle: Empty Body\n---\n")
    (v / "malformed-frontmatter.md").write_text("---\ntitle: [unclosed\n---\nBody.")

    # Excluded paths — should NOT be returned
    obsidian_dir = v / ".obsidian"
    obsidian_dir.mkdir()
    (obsidian_dir / "workspace.json").write_text("{}")
    (obsidian_dir / "config.json").write_text("{}")

    trash_dir = v / ".trash"
    trash_dir.mkdir()
    (trash_dir / "old-note.md").write_text("Deleted note.")

    templates_dir = v / "templates"
    templates_dir.mkdir()
    (templates_dir / "daily.md").write_text("Daily template.")

    # Non-markdown file — should be ignored
    (v / "image.png").write_bytes(b"\x89PNG")

    return v


# ---------------------------------------------------------------------------
# Full scan
# ---------------------------------------------------------------------------


async def test_full_scan_yields_all_md_files(vault: Path, tmp_path: Path) -> None:
    connector = _make_connector(vault, tmp_path)
    docs = [doc async for doc in connector.fetch()]
    # 7 top-level notes + 2 subdir + 1 empty-body + 1 malformed = 11 markdown files
    assert len(docs) == 11


async def test_full_scan_respects_exclude_obsidian(vault: Path, tmp_path: Path) -> None:
    connector = _make_connector(vault, tmp_path)
    docs = [doc async for doc in connector.fetch()]
    paths = [doc.metadata.source_id for doc in docs]
    assert not any(".obsidian" in p for p in paths)


async def test_full_scan_respects_exclude_trash(vault: Path, tmp_path: Path) -> None:
    connector = _make_connector(vault, tmp_path)
    docs = [doc async for doc in connector.fetch()]
    paths = [doc.metadata.source_id for doc in docs]
    assert not any(".trash" in p for p in paths)


async def test_full_scan_respects_exclude_templates(vault: Path, tmp_path: Path) -> None:
    connector = _make_connector(vault, tmp_path)
    docs = [doc async for doc in connector.fetch()]
    paths = [doc.metadata.source_id for doc in docs]
    assert not any("templates" in p for p in paths)


async def test_full_scan_ignores_non_markdown(vault: Path, tmp_path: Path) -> None:
    connector = _make_connector(vault, tmp_path)
    docs = [doc async for doc in connector.fetch()]
    paths = [doc.metadata.source_id for doc in docs]
    assert not any(p.endswith(".png") for p in paths)


async def test_full_scan_source_type(vault: Path, tmp_path: Path) -> None:
    connector = _make_connector(vault, tmp_path)
    docs = [doc async for doc in connector.fetch()]
    assert all(doc.metadata.source_type == SourceType.OBSIDIAN_NOTE for doc in docs)


async def test_full_scan_uses_frontmatter_title(vault: Path, tmp_path: Path) -> None:
    connector = _make_connector(vault, tmp_path)
    docs = {doc.metadata.source_id: doc async for doc in connector.fetch()}
    assert docs["note-1.md"].metadata.title == "Note One"
    assert docs["projects/alpha.md"].metadata.title == "Alpha Project"


async def test_full_scan_falls_back_to_filename(vault: Path, tmp_path: Path) -> None:
    connector = _make_connector(vault, tmp_path)
    docs = {doc.metadata.source_id: doc async for doc in connector.fetch()}
    assert docs["note-3.md"].metadata.title == "note-3"


async def test_full_scan_tags_populated(vault: Path, tmp_path: Path) -> None:
    connector = _make_connector(vault, tmp_path)
    docs = {doc.metadata.source_id: doc async for doc in connector.fetch()}
    assert "work" in docs["note-1.md"].metadata.tags
    assert "alpha" in docs["note-1.md"].metadata.tags


async def test_full_scan_empty_vault(tmp_path: Path) -> None:
    vault = tmp_path / "empty-vault"
    vault.mkdir()
    connector = _make_connector(vault, tmp_path)
    docs = [doc async for doc in connector.fetch()]
    assert docs == []


# ---------------------------------------------------------------------------
# Incremental: second fetch only returns changed files
# ---------------------------------------------------------------------------


async def test_incremental_only_modified_file_returned(vault: Path, tmp_path: Path) -> None:
    connector = _make_connector(vault, tmp_path)

    # First scan — ingest everything
    first_docs = [doc async for doc in connector.fetch()]
    assert len(first_docs) == 11

    # Second scan with no changes — nothing returned
    second_docs = [doc async for doc in connector.fetch()]
    assert second_docs == []


async def test_incremental_modified_file_returned(vault: Path, tmp_path: Path) -> None:
    connector = _make_connector(vault, tmp_path)

    # First scan — exhaust the generator so file state is fully persisted
    _ = [doc async for doc in connector.fetch()]

    # Modify note-7
    note7 = vault / "note-7.md"
    note7.write_text("Updated content for note seven.")
    # Force mtime to a clearly different value (add 2 s) to avoid sub-second
    # resolution issues on network / FAT filesystems.
    new_mtime = note7.stat().st_mtime + 2.0
    os.utime(note7, (new_mtime, new_mtime))

    modified_docs = [doc async for doc in connector.fetch()]
    assert len(modified_docs) == 1
    assert modified_docs[0].metadata.source_id == "note-7.md"


# ---------------------------------------------------------------------------
# Deletions
# ---------------------------------------------------------------------------


async def test_fetch_deleted_ids_after_removal(vault: Path, tmp_path: Path) -> None:
    connector = _make_connector(vault, tmp_path)

    # First full scan to establish state
    _ = [doc async for doc in connector.fetch()]

    # Delete a note
    (vault / "note-6.md").unlink()

    deleted_ids = await connector.fetch_deleted_ids()
    assert len(deleted_ids) == 1


async def test_fetch_deleted_ids_multiple(vault: Path, tmp_path: Path) -> None:
    connector = _make_connector(vault, tmp_path)
    _ = [doc async for doc in connector.fetch()]

    (vault / "note-6.md").unlink()
    (vault / "note-7.md").unlink()

    deleted_ids = await connector.fetch_deleted_ids()
    assert len(deleted_ids) == 2


async def test_fetch_deleted_ids_empty_before_sync(vault: Path, tmp_path: Path) -> None:
    """Before any fetch, there is no file state → no deletions."""
    connector = _make_connector(vault, tmp_path)
    deleted_ids = await connector.fetch_deleted_ids()
    assert deleted_ids == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_empty_body_note_handled(vault: Path, tmp_path: Path) -> None:
    """Notes with frontmatter-only bodies should not raise."""
    connector = _make_connector(vault, tmp_path)
    docs = {doc.metadata.source_id: doc async for doc in connector.fetch()}
    assert "empty-body.md" in docs
    assert docs["empty-body.md"].metadata.title == "Empty Body"


async def test_malformed_frontmatter_handled(vault: Path, tmp_path: Path) -> None:
    """Notes with malformed YAML frontmatter should be parsed without error."""
    connector = _make_connector(vault, tmp_path)
    docs = {doc.metadata.source_id: doc async for doc in connector.fetch()}
    assert "malformed-frontmatter.md" in docs
