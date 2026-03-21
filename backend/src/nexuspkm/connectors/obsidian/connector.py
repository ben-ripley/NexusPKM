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
import os
import urllib.parse
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
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
        self._last_sync_errors: list[str] = []
        self._watcher_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def vault_path(self) -> Path:
        """Absolute path to the configured Obsidian vault."""
        return self._vault_path

    @property
    def watcher_running(self) -> bool:
        """True if the filesystem watcher background task is active."""
        return self._watcher_task is not None

    def update_sync_interval(self, minutes: int) -> None:
        """Update the sync interval in the connector's in-memory config.

        This does NOT persist the change; the scheduler must also be rescheduled.
        The update is applied atomically by replacing the whole config object, so
        a concurrent scheduler read sees either the old or the new config, never a
        partially-mutated one.
        """
        self._config = ObsidianConnectorConfig(
            enabled=self._config.enabled,
            vault_path=self._config.vault_path,
            sync_interval_minutes=minutes,
            exclude_patterns=self._config.exclude_patterns,
            include_extensions=self._config.include_extensions,
        )

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
        """Return doc IDs for notes that have been deleted from the vault.

        Also removes the corresponding entries from the persisted file state so
        repeated calls do not re-report the same deletions.

        Deletion is detected by checking whether each previously-tracked path still
        exists on disk.  Intentionally does *not* use ``_collect_vault_paths`` so that
        extension-filter changes (e.g. removing ``.md`` from ``include_extensions``)
        don't cause every tracked file to be re-reported as deleted.
        """
        file_state = await self._load_file_state()
        if not file_state:
            return []

        vault_root = self._vault_path
        current_paths: set[str] = await asyncio.to_thread(
            lambda: {rel for rel in file_state if (vault_root / rel).exists()}
        )

        deleted_ids: list[str] = []
        updated_state = {
            rel_path: entry for rel_path, entry in file_state.items() if rel_path in current_paths
        }
        for rel_path, entry in file_state.items():
            if rel_path not in current_paths:
                deleted_ids.append(entry["doc_id"])
                log.info(
                    "obsidian_connector.file_deleted",
                    path=rel_path,
                    doc_id=entry["doc_id"],
                )

        if deleted_ids:
            await self._save_file_state(updated_state)

        return deleted_ids

    async def health_check(self) -> ConnectorStatus:
        """Return current health status."""
        exists = await asyncio.to_thread(
            lambda: self._vault_path.exists() and self._vault_path.is_dir()
        )
        # Use the persisted file-state cache as the source of truth for document
        # count — it survives server restarts unlike the in-memory counter.
        file_state = await self._load_file_state()
        docs_count = len(file_state)
        if not exists:
            return ConnectorStatus(
                name=self.name,
                status="unavailable",
                last_error=f"Vault not found: {self._vault_path}",
                documents_synced=docs_count,
                sync_errors=list(self._last_sync_errors),
            )
        return ConnectorStatus(
            name=self.name,
            status="healthy" if not self._last_sync_errors else "degraded",
            documents_synced=docs_count,
            sync_errors=list(self._last_sync_errors),
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
        on_upsert: Callable[[Document], Awaitable[Any]],
        on_delete: Callable[[str], Awaitable[None]],
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
        on_upsert: Callable[[Document], Awaitable[Any]],
        on_delete: Callable[[str], Awaitable[None]],
    ) -> None:
        """Internal loop using watchfiles.awatch with 2 s debounce.

        Always clears ``_watcher_task`` on exit so that ``watcher_running``
        reflects reality even if the loop terminates unexpectedly (e.g.
        inotify limit exceeded, vault unmounted).
        """
        try:
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

                    if change_type == watchfiles.Change.deleted:
                        await self._handle_delete(path, on_delete)
                    else:
                        await self._handle_upsert(path, on_upsert)
        except Exception:
            log.error(
                "obsidian_connector.watcher_crashed",
                vault=str(self._vault_path),
                exc_info=True,
            )
        finally:
            self._watcher_task = None

    async def _handle_upsert(
        self,
        path: Path,
        on_upsert: Callable[[Document], Awaitable[Any]],
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
        on_delete: Callable[[str], Awaitable[None]],
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
        # `since` is accepted for API symmetry with BaseConnector but is intentionally
        # unused: change detection relies entirely on the per-file mtime/content-hash
        # cache, which is more reliable than a bare timestamp comparison (handles clock
        # skew and sub-second writes on coarse-resolution filesystems).
        _ = since
        # Clear errors from the previous run so health_check reflects only the latest sync.
        self._last_sync_errors = []
        # NOTE: watcher (_handle_upsert/_handle_delete) can write file state concurrently
        # with this generator.  For v1 (local, single-user) the worst outcome is a
        # harmless re-index of a note on the next scheduled run; no index documents are lost.
        # A future multi-user version should add an asyncio.Lock around all file-state I/O.
        file_state = await self._load_file_state()
        vault_paths = await asyncio.to_thread(self._collect_vault_paths)

        try:
            for path in vault_paths:
                try:
                    rel = str(path.relative_to(self._vault_path))
                except ValueError:
                    continue

                stat = await asyncio.to_thread(path.stat)
                mtime = stat.st_mtime

                existing = file_state.get(rel)
                # mtime equality check: fast path for unchanged files.
                # On low-resolution filesystems (FAT32 = 2 s, some network FSes)
                # two distinct versions written within the resolution window will
                # compare equal here — the content hash below is the safety net.
                if existing is not None and existing["mtime"] == mtime:
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

                    doc = await asyncio.to_thread(self._build_document, path, content, stat)
                    file_state[rel] = _ObsidianFileEntry(
                        doc_id=doc.id,
                        mtime=mtime,
                        content_hash=content_hash,
                    )
                    self._total_docs_synced += 1
                    yield doc

                except Exception as exc:
                    self._last_sync_errors.append(f"{rel}: {exc}")
                    log.warning(
                        "obsidian_connector.file_read_failed",
                        path=str(path),
                        exc_info=True,
                    )
        finally:
            # Persist state regardless of whether the caller exhausts the generator
            # or breaks early (e.g. exception in the index layer).
            await self._save_file_state(file_state)

    # ------------------------------------------------------------------
    # Private: vault scanning
    # ------------------------------------------------------------------

    def _collect_vault_paths(self) -> list[Path]:
        """Return all matching vault files as a list.

        Intended to be called via ``asyncio.to_thread`` to avoid blocking
        the event loop during directory traversal.
        """
        results: list[Path] = []
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
            results.append(p)
        return results

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
        """Read *path* from disk and return a canonical Document.

        Used by the filesystem watcher where content is not pre-fetched.
        The main fetch pipeline uses ``_build_document`` to avoid re-reading.
        """
        raw = path.read_text(encoding="utf-8", errors="replace")
        stat = path.stat()
        return self._build_document(path, raw, stat)

    def _build_document(self, path: Path, content: str, stat: os.stat_result) -> Document:
        """Build a canonical Document from pre-read *content* and *stat* data."""
        parsed = parse_obsidian_note(content, path.stem)

        now = datetime.datetime.now(tz=datetime.UTC)
        mtime = datetime.datetime.fromtimestamp(stat.st_mtime, tz=datetime.UTC)
        ctime = datetime.datetime.fromtimestamp(stat.st_ctime, tz=datetime.UTC)

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

        plain = parsed.plain_content or title

        abs_path = str(self._vault_path / source_id)
        obsidian_url = "obsidian://open?path=" + urllib.parse.quote(abs_path, safe="")

        return Document(
            id=doc_id,
            content=plain,
            metadata=DocumentMetadata(
                source_type=SourceType.OBSIDIAN_NOTE,
                source_id=source_id,
                title=title,
                tags=parsed.tags,
                created_at=created_at,
                updated_at=updated_at,
                synced_at=now,
                url=obsidian_url,  # type: ignore[arg-type]
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
        """Atomically persist the per-file state cache to disk.

        Writes to a sibling ``.tmp`` file then renames to the final path so that
        a crash or OOM mid-write never leaves a truncated JSON file.
        """
        state_file = self._file_state_file
        serialized = json.dumps({k: dict(v) for k, v in state.items()}, indent=2)

        def _write() -> None:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = state_file.with_suffix(".tmp")
            tmp.write_text(serialized)
            tmp.replace(state_file)

        await asyncio.to_thread(_write)
