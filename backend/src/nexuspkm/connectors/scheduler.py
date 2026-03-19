"""SyncScheduler — drives periodic connector sync via APScheduler.

Each registered connector gets one interval job.  Failures in any connector
are caught, logged, and reflected as status updates; they never propagate to
the scheduler or affect other connectors.

Spec: ADR-004
"""

from __future__ import annotations

import asyncio
import datetime

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from nexuspkm.connectors.base import ConnectorStatus
from nexuspkm.connectors.registry import ConnectorRegistry
from nexuspkm.engine.index import KnowledgeIndex
from nexuspkm.models.document import SyncState

log = structlog.get_logger(__name__)


class SyncScheduler:
    """Wraps APScheduler and drives periodic sync for all registered connectors."""

    def __init__(self, registry: ConnectorRegistry, index: KnowledgeIndex) -> None:
        self._registry = registry
        self._index = index
        self._scheduler = AsyncIOScheduler()
        # Tracks in-flight sync tasks so shutdown() can await their completion
        # before the stores they write to are closed.
        self._tasks: set[asyncio.Task[None]] = set()

    def start(self, intervals: dict[str, int]) -> None:
        """Schedule one interval job per connector that appears in *intervals*.

        *intervals* maps connector name → sync period in seconds.
        Connectors not listed in *intervals* are not scheduled.
        Calling start() when the scheduler is already running is a no-op.
        """
        if self._scheduler.running:
            return

        for connector in self._registry.all_connectors():
            seconds = intervals.get(connector.name)
            if seconds is None:
                continue
            self._scheduler.add_job(
                self._tracked_sync_connector,
                "interval",
                seconds=seconds,
                args=[connector.name],
                id=f"sync_{connector.name}",
                replace_existing=True,
            )
            log.info(
                "sync_job_scheduled",
                connector=connector.name,
                interval_seconds=seconds,
            )
        self._scheduler.start()

    async def shutdown(self) -> None:
        """Stop the scheduler and await all in-flight sync tasks.

        Stops APScheduler from dispatching new jobs, then awaits any currently
        running sync coroutines so that in-progress store writes complete before
        the vector/graph stores are closed by the lifespan teardown.
        """
        self._scheduler.shutdown(wait=False)
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _tracked_sync_connector(self, name: str) -> None:
        """APScheduler job entry point — registers the current task for shutdown tracking."""
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        try:
            await self._sync_connector(name)
        finally:
            if task is not None:
                self._tasks.discard(task)

    async def _sync_connector(self, name: str) -> None:
        """Perform one sync cycle for the named connector.

        Steps:
        1. Authenticate — on False or exception: mark degraded/unavailable, return.
        2. Fetch documents since last sync — ingest each via KnowledgeIndex.insert.
        3. Persist new SyncState with updated last_synced_at.
        4. Run health_check and push result to registry.

        Any exception in steps 2-4 is caught, logged, and reflected as an
        unavailable status; the scheduler job will fire again on the next interval.
        """
        connector = self._registry.get(name)
        if connector is None:
            log.warning("sync_connector_not_found", connector=name)
            return

        # --- Step 1: authenticate ---
        try:
            authed = await connector.authenticate()
        except Exception as exc:
            log.warning(
                "connector_auth_error",
                connector=name,
                error=str(exc),
                exc_info=True,
            )
            self._registry.update_status(
                name,
                ConnectorStatus(name=name, status="unavailable", last_error=str(exc)),
            )
            return

        if not authed:
            log.warning("connector_auth_failed", connector=name)
            self._registry.update_status(
                name,
                ConnectorStatus(name=name, status="degraded", last_error="auth returned False"),
            )
            return

        # --- Steps 2-4: fetch, ingest, update state ---
        # health_check() is called before restore_sync_state() so that if the
        # health check raises, the sync cursor is NOT advanced and the next run
        # will re-fetch from the previous checkpoint (relying on idempotent inserts).
        docs_synced = 0
        try:
            sync_state = await connector.get_sync_state()
            since = sync_state.last_synced_at
            async for doc in connector.fetch(since):
                await self._index.insert(doc)
                docs_synced += 1

            health_status = await connector.health_check()

            await connector.restore_sync_state(
                SyncState(
                    last_synced_at=datetime.datetime.now(tz=datetime.UTC),
                )
            )

            self._registry.update_status(name, health_status)

            log.info(
                "connector_sync_complete",
                connector=name,
                documents_synced=docs_synced,
            )

        except Exception as exc:
            log.error(
                "connector_sync_error",
                connector=name,
                error=str(exc),
                docs_synced_before_error=docs_synced,
                exc_info=True,
            )
            self._registry.update_status(
                name,
                ConnectorStatus(name=name, status="unavailable", last_error=str(exc)),
            )
