"""Obsidian Notes Connector — ingests markdown notes from an Obsidian vault.

Scans the vault on startup and on a configurable interval.  Detects new,
modified, and deleted files by maintaining a JSON file-state cache keyed by
relative path.  Optionally watches the filesystem in real-time via
``watchfiles.awatch``.

Spec: F-004
NXP-49, NXP-58
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import fnmatch
import hashlib
import json
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Coroutine, Generator
from pathlib import Path
from typing import Any, TypedDict, cast

import structlog

from nexuspkm.config.models import ObsidianConnectorConfig
from nexuspkm.connectors.base import BaseConnector, ConnectorStatus
from nexuspkm.connectors.obsidian.markdown_parser import parse_obsidian_note
from nexuspkm.models.document import Document, DocumentMetadata, SourceType, SyncState

log = structlog.get_logger(__name__)


class _ObsidianFileEntry(TypedDict):
    doc_id: str
    mtime: float
    content_hash: str


class ObsidianNotesConnector(BaseConnector):
    """Ingests markdown notes from a local Obsidian vault."""

    name = "obsidian"

    def __init__(
        self,
        vault_path: Path,
        state_dir: Path,
        config: ObsidianConnectorConfig,
    ) -> None:
        self._vault_path = vault_path
        self._state_dir = state_dir
        self._config = config
        self._state_file = state_dir / "obsidian_sync_state.json"
        self._file_state_file = state_dir / "obsidian_file_state.json"
        self._total_docs_synced = 0
        self._watcher_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    async def authenticate(self) -> bool:
        """Return True if the vault directory exists and is readable."""
        return await asyncio.to_thread(
            lambda: self._vault_path.exists() and self._vault_path.is_dir()
        )

    def fetch(self, since: datetime.datetime | None = None) -> AsyncIterator[Document]:
        """Return an async iterator of new/modified Documents since *since*."""
        return self._fetch_gen(since)

    async def fetch_deleted_ids(self, since: datetime.datetime | None = None) -> list[str]:
        """Return doc IDs for notes that have been deleted from the vault."""
        file_state = await self._load_file_state()
        if not file_state:
            return []

        current_paths: set[str] = set()
        for path in self._scan_vault():
            try:
                rel = str(path.relative_to(self._vault_path))
            except ValueError:
                continue
            current_paths.add(rel)

        deleted_ids: list[str] = []
        for rel_path, entry in file_state.items():
            if rel_path not in current_paths:
                deleted_ids.append(entry["doc_id"])
                log.info(
                    "obsidian_connector.file_deleted",
                    path=rel_path,
                    doc_id=entry["doc_id"],
                )
        return deleted_ids

    async def health_check(self) -> ConnectorStatus:
        """Return current health status."""
        exists = await asyncio.to_thread(
            lambda: self._vault_path.exists() and self._vault_path.is_dir()
        )
        if not exists:
            return ConnectorStatus(
                name=self.name,
                status="unavailable",
                last_error=f"Vault not found: {self._vault_path}",
                documents_synced=self._total_docs_synced,
            )
        return ConnectorStatus(
            name=self.name,
            status="healthy",
            documents_synced=self._total_docs_synced,
        )

    async def get_sync_state(self) -> SyncState:
        """Load sync state from disk; return empty state if missing."""
        state_file = self._state_file

        def _read() -> SyncState:
            if not state_file.exists():
                return SyncState()
            try:
                data = json.loads(state_file.read_text())
                return SyncState.model_validate(data)
            except (json.JSONDecodeError, ValueError):
                log.warning("obsidian_connector.state_load_failed", path=str(state_file))
                return SyncState()

        return await asyncio.to_thread(_read)

    async def restore_sync_state(self, state: SyncState) -> None:
        """Persist sync state to disk."""
        state_file = self._state_file
        serialized = state.model_dump_json()

        def _write() -> None:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(serialized)

        await asyncio.to_thread(_write)

    # ------------------------------------------------------------------
    # Filesystem watcher
    # ------------------------------------------------------------------

    async def start_watching(
        self,
        on_upsert: Callable[[Document], Coroutine[Any, Any, Any]],
        on_delete: Callable[[str], Coroutine[Any, Any, Any]],
    ) -> None:
        """Start a background task watching the vault for filesystem changes.

        Args:
            on_upsert: Async callable invoked with each new/modified Document.
            on_delete: Async callable invoked with the doc_id of deleted notes.
        """
        if self._watcher_task is not None:
            return

        self._watcher_task = asyncio.create_task(
            self._watch_loop(on_upsert, on_delete),
            name="obsidian_watcher",
        )
        log.info("obsidian_connector.watcher_started", vault=str(self._vault_path))

    async def stop_watching(self) -> None:
        """Cancel the filesystem watcher task."""
        if self._watcher_task is None:
            return
        self._watcher_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._watcher_task
        self._watcher_task = None
        log.info("obsidian_connector.watcher_stopped")

    async def _watch_loop(
        self,
        on_upsert: Callable[[Document], Coroutine[Any, Any, Any]],
        on_delete: Callable[[str], Coroutine[Any, Any, Any]],
    ) -> None:
        """Internal loop using watchfiles.awatch with 2 s debounce."""
        try:
            import watchfiles
        except ImportError:
            log.error(
                "obsidian_connector.watchfiles_not_installed",
                hint="Add watchfiles>=0.21 to dependencies",
            )
            return

        async for changes in watchfiles.awatch(self._vault_path, debounce=2000):
            for change_type, path_str in changes:
                path = Path(path_str)
                if not self._should_process_path(path):
                    continue

                # watchfiles Change enum: 1=added, 2=modified, 3=deleted
                if change_type.value == 3:
                    await self._handle_delete(path, on_delete)
                else:
                    await self._handle_upsert(path, on_upsert)

    async def _handle_upsert(
        self,
        path: Path,
        on_upsert: Callable[[Document], Coroutine[Any, Any, Any]],
    ) -> None:
        try:
            doc = await asyncio.to_thread(self._to_document, path)
            await on_upsert(doc)
            self._total_docs_synced += 1
        except Exception:
            log.warning(
                "obsidian_connector.upsert_failed",
                path=str(path),
                exc_info=True,
            )

    async def _handle_delete(
        self,
        path: Path,
        on_delete: Callable[[str], Coroutine[Any, Any, Any]],
    ) -> None:
        try:
            rel = str(path.relative_to(self._vault_path))
            file_state = await self._load_file_state()
            entry = file_state.pop(rel, None)
            if entry is not None:
                await on_delete(entry["doc_id"])
                await self._save_file_state(file_state)
        except Exception:
            log.warning(
                "obsidian_connector.delete_failed",
                path=str(path),
                exc_info=True,
            )

    def _should_process_path(self, path: Path) -> bool:
        """Return True if this path should trigger an upsert/delete event."""
        try:
            rel = str(path.relative_to(self._vault_path))
        except ValueError:
            return False
        if self._is_excluded(rel):
            return False
        suffix = path.suffix.lower()
        return suffix in self._config.include_extensions

    # ------------------------------------------------------------------
    # Private: fetch pipeline
    # ------------------------------------------------------------------

    async def _fetch_gen(self, since: datetime.datetime | None) -> AsyncGenerator[Document, None]:
        file_state = await self._load_file_state()

        for path in self._scan_vault():
            try:
                rel = str(path.relative_to(self._vault_path))
            except ValueError:
                continue

            stat = await asyncio.to_thread(path.stat)
            mtime = stat.st_mtime

            existing = file_state.get(rel)
            if existing is not None and existing["mtime"] == mtime:
                # Quick mtime check: no change
                continue

            try:
                content = await asyncio.to_thread(path.read_text, "utf-8", "replace")
                content_hash = hashlib.sha256(content.encode()).hexdigest()

                if existing is not None and existing["content_hash"] == content_hash:
                    # mtime changed but content identical — skip, update mtime
                    file_state[rel] = _ObsidianFileEntry(
                        doc_id=existing["doc_id"],
                        mtime=mtime,
                        content_hash=content_hash,
                    )
                    continue

                doc = await asyncio.to_thread(self._to_document, path)
                file_state[rel] = _ObsidianFileEntry(
                    doc_id=doc.id,
                    mtime=mtime,
                    content_hash=content_hash,
                )
                self._total_docs_synced += 1
                yield doc

            except Exception:
                log.warning(
                    "obsidian_connector.file_read_failed",
                    path=str(path),
                    exc_info=True,
                )

        await self._save_file_state(file_state)

    # ------------------------------------------------------------------
    # Private: vault scanning
    # ------------------------------------------------------------------

    def _scan_vault(self) -> Generator[Path, None, None]:
        """Yield Path objects for all matching files in the vault."""
        for p in self._vault_path.rglob("*"):
            if not p.is_file():
                continue
            try:
                rel = str(p.relative_to(self._vault_path))
            except ValueError:
                continue
            if self._is_excluded(rel):
                continue
            if p.suffix.lower() not in self._config.include_extensions:
                continue
            yield p

    def _is_excluded(self, rel_path: str) -> bool:
        """Return True if *rel_path* matches any configured exclude pattern."""
        for pattern in self._config.exclude_patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            # Also check if any path component matches the pattern prefix
            # e.g. ".obsidian/" matches ".obsidian/config" and "a/.obsidian/b"
            pat = pattern.rstrip("/")
            parts = rel_path.replace("\\", "/").split("/")
            for i in range(len(parts)):
                segment = "/".join(parts[: i + 1])
                if fnmatch.fnmatch(segment, pat) or fnmatch.fnmatch(segment + "/", pattern):
                    return True
                if fnmatch.fnmatch(parts[i], pat):
                    return True
        return False

    # ------------------------------------------------------------------
    # Private: document transformation
    # ------------------------------------------------------------------

    def _to_document(self, path: Path) -> Document:
        """Parse an Obsidian note file and return a canonical Document."""
        raw = path.read_text(encoding="utf-8", errors="replace")
        parsed = parse_obsidian_note(raw, path.stem)

        now = datetime.datetime.now(tz=datetime.UTC)
        try:
            stat = path.stat()
            mtime = datetime.datetime.fromtimestamp(stat.st_mtime, tz=datetime.UTC)
            ctime = datetime.datetime.fromtimestamp(stat.st_ctime, tz=datetime.UTC)
        except OSError:
            mtime = now
            ctime = now

        # Use created_at <= updated_at: if ctime > mtime, fall back to mtime for both
        created_at = min(ctime, mtime)
        updated_at = mtime

        fm_title = parsed.frontmatter.get("title")
        title = fm_title.strip() if isinstance(fm_title, str) and fm_title.strip() else path.stem

        try:
            rel = path.relative_to(self._vault_path)
        except ValueError:
            rel = Path(path.name)

        doc_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"obsidian:{rel}"))
        source_id = str(rel)

        content = parsed.plain_content or title

        return Document(
            id=doc_id,
            content=content,
            metadata=DocumentMetadata(
                source_type=SourceType.OBSIDIAN_NOTE,
                source_id=source_id,
                title=title,
                tags=parsed.tags,
                created_at=created_at,
                updated_at=updated_at,
                synced_at=now,
                custom={
                    "wikilinks": parsed.wikilinks,
                    "embeds": parsed.embeds,
                    "vault_path": str(self._vault_path),
                },
            ),
        )

    # ------------------------------------------------------------------
    # Private: file state persistence
    # ------------------------------------------------------------------

    async def _load_file_state(self) -> dict[str, _ObsidianFileEntry]:
        """Load the per-file state cache from disk."""
        state_file = self._file_state_file

        def _read() -> dict[str, _ObsidianFileEntry]:
            if not state_file.exists():
                return {}
            try:
                raw = json.loads(state_file.read_text())
                if not isinstance(raw, dict):
                    return {}
                return {
                    k: cast(_ObsidianFileEntry, v) for k, v in raw.items() if isinstance(v, dict)
                }
            except (json.JSONDecodeError, ValueError, TypeError):
                log.warning("obsidian_connector.file_state_load_failed", path=str(state_file))
                return {}

        return await asyncio.to_thread(_read)

    async def _save_file_state(self, state: dict[str, _ObsidianFileEntry]) -> None:
        """Persist the per-file state cache to disk."""
        state_file = self._file_state_file
        serialized = json.dumps({k: dict(v) for k, v in state.items()}, indent=2)

        def _write() -> None:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(serialized)

        await asyncio.to_thread(_write)
