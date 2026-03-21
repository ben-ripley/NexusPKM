"""Apple Notes Connector — ingests notes from Apple Notes via osascript.

Uses JXA (JavaScript for Automation) via ``osascript -l JavaScript`` as the
primary extraction method, with the NoteStore SQLite database as a fallback.

Platform: macOS only.  ``authenticate()`` returns ``False`` on other platforms;
the connector is gracefully skipped in that case.

Spec: F-009
NXP-68
"""

from __future__ import annotations

import asyncio
import datetime
import json
import sqlite3
import subprocess
import sys
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path
from typing import Any, TypedDict, cast

import structlog

from nexuspkm.config.models import AppleNotesConnectorConfig
from nexuspkm.connectors.apple_notes.html_converter import convert_html_to_markdown
from nexuspkm.connectors.base import BaseConnector, ConnectorStatus
from nexuspkm.models.document import Document, DocumentMetadata, SourceType, SyncState

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# AppleScript / JXA script
# ---------------------------------------------------------------------------

# JXA script that produces a JSON array of note objects.
# Runs via: osascript -l JavaScript -e <script>
_JXA_SCRIPT = """\
const app = Application('Notes');
const notes = app.notes();
const result = [];
for (let i = 0; i < notes.length; i++) {
    try {
        const note = notes[i];
        result.push({
            id: note.id(),
            name: note.name(),
            body: note.body(),
            folder: note.container().name(),
            created: note.creationDate().toISOString(),
            modified: note.modificationDate().toISOString()
        });
    } catch(e) {}
}
JSON.stringify(result);
"""

# ---------------------------------------------------------------------------
# SQLite query constants
# ---------------------------------------------------------------------------

_SQLITE_QUERY = """\
SELECT
    n.ZNOTE as note_id,
    n.ZTITLE as title,
    nb.ZDATA as body_data,
    f.ZTITLE as folder_name,
    n.ZCREATIONDATE as created,
    n.ZMODIFICATIONDATE as modified
FROM ZICCLOUDSYNCINGOBJECT n
JOIN ZNOTEBODY nb ON n.ZBODY = nb.Z_PK
LEFT JOIN ZICCLOUDSYNCINGOBJECT f ON n.ZFOLDER = f.Z_PK
WHERE n.ZMARKEDFORDELETION != 1
"""

# Core Data timestamps are seconds since 2001-01-01 00:00:00 UTC.
_CORE_DATA_EPOCH = datetime.datetime(2001, 1, 1, tzinfo=datetime.UTC)

# Default path to the NoteStore SQLite database on macOS.
_NOTES_DB_PATH = Path.home() / "Library/Group Containers/group.com.apple.notes/NoteStore.sqlite"


# ---------------------------------------------------------------------------
# State TypedDict
# ---------------------------------------------------------------------------


class _AppleNoteEntry(TypedDict):
    """Per-note sync state entry."""

    doc_id: str
    modified: str  # ISO-8601 datetime string from JXA .toISOString()


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


class AppleNotesConnector(BaseConnector):
    """Ingests notes from Apple Notes on macOS."""

    name = "apple_notes"

    def __init__(
        self,
        state_dir: Path,
        config: AppleNotesConnectorConfig,
    ) -> None:
        self._state_dir = state_dir
        self._config = config
        self._note_state_file = state_dir / "apple_notes_sync_state.json"
        self._checkpoint_file = state_dir / "apple_notes_checkpoint.json"
        self._total_docs_synced = 0
        self._last_sync_errors: list[str] = []

    def update_sync_interval(self, minutes: int) -> None:
        """Update the sync interval in-memory.  Caller must reschedule the job."""
        self._config = AppleNotesConnectorConfig(
            enabled=self._config.enabled,
            sync_interval_minutes=minutes,
            extraction_method=self._config.extraction_method,
        )

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    async def authenticate(self) -> bool:
        """Return False on non-macOS; True otherwise.

        On macOS, osascript will trigger the system permission dialog on first
        use — the connector does not pre-validate Notes access here to avoid
        blocking the startup sequence.
        """
        return sys.platform == "darwin"

    def fetch(self, since: datetime.datetime | None = None) -> AsyncIterator[Document]:
        return self._fetch_gen(since)

    async def fetch_deleted_ids(self, since: datetime.datetime | None = None) -> list[str]:
        """Return doc IDs for notes that were deleted since the last sync.

        Compares the persisted note state against the current live note list.
        Stale entries are removed from state so repeated calls do not
        re-report the same deletions.
        """
        _ = since
        note_state = await self._load_note_state()
        if not note_state:
            return []

        try:
            raw_notes = await self._fetch_notes()
        except Exception as exc:
            log.warning(
                "apple_notes_connector.fetch_deleted_ids_error",
                error=str(exc),
                exc_info=True,
            )
            return []

        current_ids = {note["id"] for note in raw_notes}
        deleted_ids: list[str] = []
        updated_state: dict[str, _AppleNoteEntry] = {}

        for note_id, entry in note_state.items():
            if note_id in current_ids:
                updated_state[note_id] = entry
            else:
                deleted_ids.append(entry["doc_id"])
                log.info(
                    "apple_notes_connector.note_deleted",
                    note_id=note_id,
                    doc_id=entry["doc_id"],
                )

        if deleted_ids:
            await self._save_note_state(updated_state)

        return deleted_ids

    async def health_check(self) -> ConnectorStatus:
        """Return current health status."""
        if sys.platform != "darwin":
            return ConnectorStatus(
                name=self.name,
                status="unavailable",
                last_error="Apple Notes connector requires macOS",
            )
        note_state = await self._load_note_state()
        return ConnectorStatus(
            name=self.name,
            status="healthy" if not self._last_sync_errors else "degraded",
            documents_synced=len(note_state),
            sync_errors=list(self._last_sync_errors),
        )

    async def get_sync_state(self) -> SyncState:
        """Load sync checkpoint from disk; return empty state if missing."""
        checkpoint_file = self._checkpoint_file

        def _read() -> SyncState:
            if not checkpoint_file.exists():
                return SyncState()
            try:
                data = json.loads(checkpoint_file.read_text())
                return SyncState.model_validate(data)
            except (json.JSONDecodeError, ValueError):
                log.warning(
                    "apple_notes_connector.checkpoint_load_failed",
                    path=str(checkpoint_file),
                )
                return SyncState()

        return await asyncio.to_thread(_read)

    async def restore_sync_state(self, state: SyncState) -> None:
        """Persist sync checkpoint to disk."""
        checkpoint_file = self._checkpoint_file
        serialized = state.model_dump_json()

        def _write() -> None:
            checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
            checkpoint_file.write_text(serialized)

        await asyncio.to_thread(_write)

    # ------------------------------------------------------------------
    # Private: fetch pipeline
    # ------------------------------------------------------------------

    async def _fetch_gen(
        self, since: datetime.datetime | None
    ) -> AsyncGenerator[Document, None]:
        _ = since
        self._last_sync_errors = []

        try:
            raw_notes = await self._fetch_notes()
        except Exception as exc:
            self._last_sync_errors.append(str(exc))
            log.error("apple_notes_connector.fetch_failed", exc_info=True)
            return

        note_state = await self._load_note_state()

        try:
            for note in raw_notes:
                note_id = note["id"]
                modified = note["modified"]

                existing = note_state.get(note_id)
                if existing is not None and existing["modified"] == modified:
                    continue

                try:
                    doc = self._to_document(note)
                    note_state[note_id] = _AppleNoteEntry(doc_id=doc.id, modified=modified)
                    self._total_docs_synced += 1
                    yield doc
                except Exception as exc:
                    self._last_sync_errors.append(f"{note_id}: {exc}")
                    log.warning(
                        "apple_notes_connector.note_transform_failed",
                        note_id=note_id,
                        exc_info=True,
                    )
        finally:
            await self._save_note_state(note_state)

    async def _fetch_notes(self) -> list[dict[str, str]]:
        """Fetch all notes via the configured extraction method."""
        if self._config.extraction_method == "sqlite":
            return await self._fetch_via_sqlite()
        return await self._fetch_via_applescript()

    async def _fetch_via_applescript(self) -> list[dict[str, str]]:
        """Fetch notes using JXA via ``osascript -l JavaScript``."""

        def _run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["osascript", "-l", "JavaScript", "-e", _JXA_SCRIPT],
                capture_output=True,
                text=True,
                timeout=120,
            )

        result = await asyncio.to_thread(_run)
        if result.returncode != 0:
            raise RuntimeError(f"osascript failed: {result.stderr.strip()}")
        return self._parse_applescript_output(result.stdout)

    def _parse_applescript_output(self, output: str) -> list[dict[str, str]]:
        """Parse the JXA JSON stdout into a list of note dicts."""
        output = output.strip()
        if not output:
            return []
        try:
            data: Any = json.loads(output)
            if not isinstance(data, list):
                return []
            return [
                {str(k): str(v) for k, v in item.items()}
                for item in data
                if isinstance(item, dict)
            ]
        except (json.JSONDecodeError, ValueError) as exc:
            log.warning("apple_notes_connector.parse_output_failed", error=str(exc))
            return []

    async def _fetch_via_sqlite(self) -> list[dict[str, str]]:
        """Fetch notes by reading NoteStore.sqlite directly (fallback method)."""
        db_path = _NOTES_DB_PATH

        def _query() -> list[dict[str, str]]:
            conn = sqlite3.connect(str(db_path))
            try:
                cursor = conn.execute(_SQLITE_QUERY)
                notes: list[dict[str, str]] = []
                for row in cursor.fetchall():
                    note_id = row[0]
                    title = row[1]
                    folder = row[3]
                    created_raw = row[4]
                    modified_raw = row[5]
                    created_dt = _CORE_DATA_EPOCH + datetime.timedelta(
                        seconds=float(created_raw or 0)
                    )
                    modified_dt = _CORE_DATA_EPOCH + datetime.timedelta(
                        seconds=float(modified_raw or 0)
                    )
                    notes.append(
                        {
                            "id": str(note_id or ""),
                            "name": str(title or "Untitled"),
                            "body": "",  # compressed in SQLite; not decoded in v1
                            "folder": str(folder or "Notes"),
                            "created": created_dt.isoformat(),
                            "modified": modified_dt.isoformat(),
                        }
                    )
                return notes
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    # ------------------------------------------------------------------
    # Private: document transformation
    # ------------------------------------------------------------------

    def _to_document(self, note: dict[str, str]) -> Document:
        """Convert a raw note dict to a canonical Document."""
        note_id = note["id"]
        title = note.get("name") or "Untitled"
        html_body = note.get("body", "")
        folder = note.get("folder", "Notes")
        created_str = note.get("created", "")
        modified_str = note.get("modified", "")

        now = datetime.datetime.now(tz=datetime.UTC)

        def _parse_dt(s: str) -> datetime.datetime:
            if not s:
                return now
            # JXA .toISOString() produces "Z" suffix; fromisoformat requires "+00:00"
            return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))

        try:
            created_at = _parse_dt(created_str)
        except ValueError:
            created_at = now
        try:
            modified_at = _parse_dt(modified_str)
        except ValueError:
            modified_at = now

        # DocumentMetadata validates updated_at >= created_at
        if modified_at < created_at:
            modified_at = created_at

        content = convert_html_to_markdown(html_body) if html_body else ""
        if not content:
            content = title

        has_images = "<img" in html_body or "<figure" in html_body
        has_checklists = "data-checked" in html_body

        doc_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"apple_note:{note_id}"))

        return Document(
            id=doc_id,
            content=content,
            metadata=DocumentMetadata(
                source_type=SourceType.APPLE_NOTE,
                source_id=note_id,
                title=title,
                tags=[],
                created_at=created_at,
                updated_at=modified_at,
                synced_at=now,
                custom={
                    "folder": folder,
                    "extraction_method": self._config.extraction_method,
                    "has_images": has_images,
                    "has_checklists": has_checklists,
                },
            ),
        )

    # ------------------------------------------------------------------
    # Private: note state persistence
    # ------------------------------------------------------------------

    async def _load_note_state(self) -> dict[str, _AppleNoteEntry]:
        """Load note state from disk; return empty dict if missing or corrupt."""
        state_file = self._note_state_file

        def _read() -> dict[str, _AppleNoteEntry]:
            if not state_file.exists():
                return {}
            try:
                raw = json.loads(state_file.read_text())
                if not isinstance(raw, dict):
                    return {}
                return {
                    k: cast(_AppleNoteEntry, v)
                    for k, v in raw.items()
                    if isinstance(v, dict)
                }
            except (json.JSONDecodeError, ValueError, TypeError):
                log.warning(
                    "apple_notes_connector.state_load_failed", path=str(state_file)
                )
                return {}

        return await asyncio.to_thread(_read)

    async def _save_note_state(self, state: dict[str, _AppleNoteEntry]) -> None:
        """Atomically persist note state.  Writes tmp then renames to prevent corruption."""
        state_file = self._note_state_file
        serialized = json.dumps({k: dict(v) for k, v in state.items()}, indent=2)

        def _write() -> None:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = state_file.with_suffix(".tmp")
            tmp.write_text(serialized)
            tmp.replace(state_file)

        await asyncio.to_thread(_write)
