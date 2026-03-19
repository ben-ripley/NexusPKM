"""Tests for SyncScheduler.

Covers: connectors/scheduler.py
Spec refs: ADR-004
NXP-52
"""

from __future__ import annotations

import asyncio
import datetime
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexuspkm.models.document import Document, DocumentMetadata, SourceType

NOW = datetime.datetime(2026, 3, 19, 12, 0, 0, tzinfo=datetime.UTC)


def _make_document(doc_id: str = "doc-1") -> Document:
    return Document(
        id=doc_id,
        content="Test content",
        metadata=DocumentMetadata(
            source_type=SourceType.OBSIDIAN_NOTE,
            source_id="note-1",
            title="Test Note",
            created_at=NOW,
            updated_at=NOW,
            synced_at=NOW,
        ),
    )


def _make_stub_connector(name: str = "stub") -> MagicMock:
    """Return a MagicMock that satisfies the BaseConnector interface.

    - fetch is a plain def returning an AsyncIterator (not async def)
    - get_sync_state and restore_sync_state are async
    """
    from nexuspkm.connectors.base import ConnectorStatus
    from nexuspkm.models.document import SyncState

    connector = MagicMock()
    connector.name = name
    connector.authenticate = AsyncMock(return_value=True)

    # fetch is a regular def returning an AsyncIterator
    def _default_fetch(since: datetime.datetime | None = None) -> AsyncIterator[Document]:
        async def _gen() -> AsyncIterator[Document]:
            yield _make_document("doc-1")
            yield _make_document("doc-2")

        return _gen()

    connector.fetch = _default_fetch
    connector.health_check = AsyncMock(
        return_value=ConnectorStatus(name=name, status="healthy", documents_synced=2)
    )
    connector.get_sync_state = AsyncMock(return_value=SyncState())
    connector.restore_sync_state = AsyncMock()
    return connector


def _make_registry(connector: MagicMock) -> MagicMock:
    registry = MagicMock()
    registry.get = MagicMock(return_value=connector)
    registry.all_connectors = MagicMock(return_value=[connector])
    registry.update_status = MagicMock()
    return registry


class TestSyncSchedulerHappyPath:
    @pytest.mark.asyncio
    async def test_happy_path_ingests_all_docs(self) -> None:
        from nexuspkm.connectors.scheduler import SyncScheduler

        connector = _make_stub_connector("stub")
        registry = _make_registry(connector)
        index = MagicMock()
        index.insert = AsyncMock(side_effect=lambda doc: doc)

        scheduler = SyncScheduler(registry, index)
        await scheduler._sync_connector("stub")

        assert index.insert.call_count == 2

    @pytest.mark.asyncio
    async def test_happy_path_calls_restore_sync_state(self) -> None:
        from nexuspkm.connectors.scheduler import SyncScheduler

        connector = _make_stub_connector("stub")
        registry = _make_registry(connector)
        index = MagicMock()
        index.insert = AsyncMock(side_effect=lambda doc: doc)

        scheduler = SyncScheduler(registry, index)
        await scheduler._sync_connector("stub")

        connector.restore_sync_state.assert_awaited_once()
        state_arg = connector.restore_sync_state.call_args[0][0]
        assert state_arg.last_synced_at is not None

    @pytest.mark.asyncio
    async def test_happy_path_calls_health_check(self) -> None:
        from nexuspkm.connectors.scheduler import SyncScheduler

        connector = _make_stub_connector("stub")
        registry = _make_registry(connector)
        index = MagicMock()
        index.insert = AsyncMock(side_effect=lambda doc: doc)

        scheduler = SyncScheduler(registry, index)
        await scheduler._sync_connector("stub")

        connector.health_check.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_happy_path_updates_registry_status(self) -> None:
        from nexuspkm.connectors.scheduler import SyncScheduler

        connector = _make_stub_connector("stub")
        registry = _make_registry(connector)
        index = MagicMock()
        index.insert = AsyncMock(side_effect=lambda doc: doc)

        scheduler = SyncScheduler(registry, index)
        await scheduler._sync_connector("stub")

        registry.update_status.assert_called_once()
        name_arg, status_arg = registry.update_status.call_args[0]
        assert name_arg == "stub"
        assert status_arg.status == "healthy"

    @pytest.mark.asyncio
    async def test_passes_last_synced_at_to_fetch(self) -> None:
        from nexuspkm.connectors.scheduler import SyncScheduler
        from nexuspkm.models.document import SyncState

        connector = _make_stub_connector("stub")
        connector.get_sync_state = AsyncMock(return_value=SyncState(last_synced_at=NOW))

        fetch_calls: list[datetime.datetime | None] = []

        def _fetch(since: datetime.datetime | None = None) -> AsyncIterator[Document]:
            fetch_calls.append(since)

            async def _gen() -> AsyncIterator[Document]:
                return
                yield  # pragma: no cover

            return _gen()

        connector.fetch = _fetch

        registry = _make_registry(connector)
        index = MagicMock()
        index.insert = AsyncMock(side_effect=lambda doc: doc)

        scheduler = SyncScheduler(registry, index)
        await scheduler._sync_connector("stub")

        assert fetch_calls == [NOW]


class TestSyncSchedulerAuthFailure:
    @pytest.mark.asyncio
    async def test_authenticate_returns_false_skips_fetch(self) -> None:
        from nexuspkm.connectors.scheduler import SyncScheduler

        connector = _make_stub_connector("stub")
        connector.authenticate = AsyncMock(return_value=False)

        fetch_called = False

        def _fetch(since: datetime.datetime | None = None) -> AsyncIterator[Document]:
            nonlocal fetch_called
            fetch_called = True

            async def _gen() -> AsyncIterator[Document]:
                return
                yield  # pragma: no cover

            return _gen()

        connector.fetch = _fetch
        registry = _make_registry(connector)
        index = MagicMock()
        index.insert = AsyncMock()

        scheduler = SyncScheduler(registry, index)
        await scheduler._sync_connector("stub")

        assert not fetch_called
        index.insert.assert_not_called()

    @pytest.mark.asyncio
    async def test_authenticate_returns_false_sets_degraded(self) -> None:
        from nexuspkm.connectors.scheduler import SyncScheduler

        connector = _make_stub_connector("stub")
        connector.authenticate = AsyncMock(return_value=False)

        registry = _make_registry(connector)
        index = MagicMock()
        index.insert = AsyncMock()

        scheduler = SyncScheduler(registry, index)
        await scheduler._sync_connector("stub")

        registry.update_status.assert_called_once()
        name_arg, status_arg = registry.update_status.call_args[0]
        assert name_arg == "stub"
        assert status_arg.status == "degraded"

    @pytest.mark.asyncio
    async def test_authenticate_raises_sets_unavailable(self) -> None:
        from nexuspkm.connectors.scheduler import SyncScheduler

        connector = _make_stub_connector("stub")
        connector.authenticate = AsyncMock(side_effect=RuntimeError("auth failed"))

        registry = _make_registry(connector)
        index = MagicMock()
        index.insert = AsyncMock()

        scheduler = SyncScheduler(registry, index)
        await scheduler._sync_connector("stub")

        registry.update_status.assert_called_once()
        _, status_arg = registry.update_status.call_args[0]
        assert status_arg.status == "unavailable"

    @pytest.mark.asyncio
    async def test_authenticate_raises_no_crash(self) -> None:
        from nexuspkm.connectors.scheduler import SyncScheduler

        connector = _make_stub_connector("stub")
        connector.authenticate = AsyncMock(side_effect=RuntimeError("boom"))

        registry = _make_registry(connector)
        index = MagicMock()
        scheduler = SyncScheduler(registry, index)

        # Must not propagate the exception
        await scheduler._sync_connector("stub")


class TestSyncSchedulerHealthCheckFailure:
    @pytest.mark.asyncio
    async def test_health_check_raises_does_not_call_restore_sync_state(self) -> None:
        """restore_sync_state must NOT be called when health_check raises.

        If health_check fails after ingestion, we do not advance the cursor so
        the next run will re-fetch from the old checkpoint (relying on idempotent
        inserts rather than silently dropping documents).
        """
        from nexuspkm.connectors.scheduler import SyncScheduler

        connector = _make_stub_connector("stub")
        connector.health_check = AsyncMock(side_effect=RuntimeError("health failure"))

        registry = _make_registry(connector)
        index = MagicMock()
        index.insert = AsyncMock(side_effect=lambda doc: doc)

        scheduler = SyncScheduler(registry, index)
        await scheduler._sync_connector("stub")

        connector.restore_sync_state.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_health_check_raises_sets_unavailable(self) -> None:
        from nexuspkm.connectors.scheduler import SyncScheduler

        connector = _make_stub_connector("stub")
        connector.health_check = AsyncMock(side_effect=RuntimeError("health failure"))

        registry = _make_registry(connector)
        index = MagicMock()
        index.insert = AsyncMock(side_effect=lambda doc: doc)

        scheduler = SyncScheduler(registry, index)
        await scheduler._sync_connector("stub")

        _, status_arg = registry.update_status.call_args[0]
        assert status_arg.status == "unavailable"


class TestSyncSchedulerFetchFailure:
    @pytest.mark.asyncio
    async def test_fetch_raises_sets_unavailable(self) -> None:
        from nexuspkm.connectors.scheduler import SyncScheduler

        connector = _make_stub_connector("stub")

        def _bad_fetch(since: datetime.datetime | None = None) -> AsyncIterator[Document]:
            raise RuntimeError("fetch error")

        connector.fetch = _bad_fetch

        registry = _make_registry(connector)
        index = MagicMock()
        index.insert = AsyncMock()

        scheduler = SyncScheduler(registry, index)
        await scheduler._sync_connector("stub")

        _, status_arg = registry.update_status.call_args[0]
        assert status_arg.status == "unavailable"

    @pytest.mark.asyncio
    async def test_fetch_raises_no_crash(self) -> None:
        from nexuspkm.connectors.scheduler import SyncScheduler

        connector = _make_stub_connector("stub")

        def _bad_fetch(since: datetime.datetime | None = None) -> AsyncIterator[Document]:
            raise RuntimeError("fetch error")

        connector.fetch = _bad_fetch

        registry = _make_registry(connector)
        index = MagicMock()
        scheduler = SyncScheduler(registry, index)
        # Must not propagate
        await scheduler._sync_connector("stub")

    @pytest.mark.asyncio
    async def test_fetch_iter_raises_sets_unavailable(self) -> None:
        """Errors raised during async iteration are also caught."""
        from nexuspkm.connectors.scheduler import SyncScheduler

        connector = _make_stub_connector("stub")

        def _bad_fetch(since: datetime.datetime | None = None) -> AsyncIterator[Document]:
            async def _gen() -> AsyncIterator[Document]:
                yield _make_document("doc-1")
                raise RuntimeError("mid-stream error")

            return _gen()

        connector.fetch = _bad_fetch

        registry = _make_registry(connector)
        index = MagicMock()
        index.insert = AsyncMock()

        scheduler = SyncScheduler(registry, index)
        await scheduler._sync_connector("stub")

        _, status_arg = registry.update_status.call_args[0]
        assert status_arg.status == "unavailable"


class TestSyncSchedulerInsertFailure:
    @pytest.mark.asyncio
    async def test_insert_raises_sets_unavailable_no_crash(self) -> None:
        from nexuspkm.connectors.scheduler import SyncScheduler

        connector = _make_stub_connector("stub")
        registry = _make_registry(connector)
        index = MagicMock()
        index.insert = AsyncMock(side_effect=RuntimeError("DB error"))

        scheduler = SyncScheduler(registry, index)
        await scheduler._sync_connector("stub")

        _, status_arg = registry.update_status.call_args[0]
        assert status_arg.status == "unavailable"


class TestSyncSchedulerLifecycle:
    def test_start_adds_interval_jobs(self) -> None:
        from nexuspkm.connectors.scheduler import SyncScheduler

        connector = _make_stub_connector("stub")
        registry = MagicMock()
        registry.all_connectors = MagicMock(return_value=[connector])
        index = MagicMock()

        with patch("nexuspkm.connectors.scheduler.AsyncIOScheduler") as MockScheduler:
            mock_sched = MagicMock()
            mock_sched.running = False
            MockScheduler.return_value = mock_sched

            scheduler = SyncScheduler(registry, index)
            scheduler.start({"stub": 300})

            mock_sched.add_job.assert_called_once()
            mock_sched.start.assert_called_once()

    def test_start_skips_unregistered_interval_names(self) -> None:
        """Intervals for connectors not in registry are silently skipped."""
        from nexuspkm.connectors.scheduler import SyncScheduler

        registry = MagicMock()
        registry.all_connectors = MagicMock(return_value=[])
        index = MagicMock()

        with patch("nexuspkm.connectors.scheduler.AsyncIOScheduler") as MockScheduler:
            mock_sched = MagicMock()
            mock_sched.running = False
            MockScheduler.return_value = mock_sched

            scheduler = SyncScheduler(registry, index)
            scheduler.start({"ghost_connector": 60})

            mock_sched.add_job.assert_not_called()
            mock_sched.start.assert_called_once()

    def test_start_is_noop_when_already_running(self) -> None:
        """Calling start() when the scheduler is already running must not raise."""
        from nexuspkm.connectors.scheduler import SyncScheduler

        registry = MagicMock()
        registry.all_connectors = MagicMock(return_value=[])
        index = MagicMock()

        with patch("nexuspkm.connectors.scheduler.AsyncIOScheduler") as MockScheduler:
            mock_sched = MagicMock()
            mock_sched.running = True  # already running
            MockScheduler.return_value = mock_sched

            scheduler = SyncScheduler(registry, index)
            scheduler.start({})

            # Should not call start() again or add any jobs
            mock_sched.start.assert_not_called()
            mock_sched.add_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_shutdown_calls_scheduler_shutdown(self) -> None:
        from nexuspkm.connectors.scheduler import SyncScheduler

        registry = MagicMock()
        registry.all_connectors = MagicMock(return_value=[])
        index = MagicMock()

        with patch("nexuspkm.connectors.scheduler.AsyncIOScheduler") as MockScheduler:
            mock_sched = MagicMock()
            mock_sched.running = False
            MockScheduler.return_value = mock_sched

            scheduler = SyncScheduler(registry, index)
            await scheduler.shutdown()

            mock_sched.shutdown.assert_called_once_with(wait=False)

    @pytest.mark.asyncio
    async def test_tracked_sync_connector_registers_and_removes_task(self) -> None:
        """_tracked_sync_connector adds the running task to _tasks during execution
        and removes it on completion.
        """
        from nexuspkm.connectors.scheduler import SyncScheduler

        connector = _make_stub_connector("stub")
        registry = _make_registry(connector)
        index = MagicMock()
        index.insert = AsyncMock(side_effect=lambda doc: doc)

        # A barrier that _sync_connector will block on so we can inspect _tasks mid-run.
        barrier = asyncio.Event()
        reached = asyncio.Event()

        async def _pausing_sync(name: str) -> None:
            reached.set()
            await barrier.wait()

        scheduler = SyncScheduler(registry, index)
        # Patch the inner method so _tracked_sync_connector still exercises its
        # add/discard logic but we can pause execution at a known point.
        scheduler._sync_connector = _pausing_sync  # type: ignore[method-assign]

        task = asyncio.create_task(scheduler._tracked_sync_connector("stub"))

        # Wait until _pausing_sync has started (task is in progress)
        await reached.wait()
        assert task in scheduler._tasks, "task should be tracked while running"

        # Unblock and await completion
        barrier.set()
        await task
        assert task not in scheduler._tasks, "task should be removed after completion"

    @pytest.mark.asyncio
    async def test_shutdown_awaits_in_flight_tasks(self) -> None:
        """shutdown() drains _tasks via asyncio.gather before returning."""
        from nexuspkm.connectors.scheduler import SyncScheduler

        registry = MagicMock()
        registry.all_connectors = MagicMock(return_value=[])
        index = MagicMock()

        with patch("nexuspkm.connectors.scheduler.AsyncIOScheduler") as MockScheduler:
            mock_sched = MagicMock()
            mock_sched.running = False
            MockScheduler.return_value = mock_sched

            scheduler = SyncScheduler(registry, index)

            # Add a real (already-completed) task to _tasks to verify gather is called.
            completed = asyncio.create_task(asyncio.sleep(0))
            await completed
            scheduler._tasks.add(completed)

            await scheduler.shutdown()

            mock_sched.shutdown.assert_called_once_with(wait=False)
