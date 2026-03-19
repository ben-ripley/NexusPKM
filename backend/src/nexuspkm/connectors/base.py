"""Abstract base class and status model for all connectors.

Every concrete connector must subclass BaseConnector and implement all
abstract methods.  The name class variable uniquely identifies the connector
in the registry and scheduler.

Spec: ADR-004
"""

from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import ClassVar, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

from nexuspkm.models.document import Document, SyncState


class ConnectorStatus(BaseModel):
    """Runtime health and sync statistics for a single connector."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    status: Literal["healthy", "degraded", "unavailable"]
    last_sync_at: AwareDatetime | None = None
    last_error: str | None = None
    documents_synced: int = 0


class BaseConnector(ABC):
    """Abstract base for all NexusPKM data source connectors.

    Subclasses must:
    - Set a unique ``name`` class variable (e.g. ``"teams"``, ``"obsidian"``).
    - Implement all abstract methods.

    ``fetch`` is a plain (non-async) method that returns an ``AsyncIterator``.
    Implementations may use async generator syntax::

        async def fetch(self, since=None):
            async for item in self._api.list(since=since):
                yield self._to_document(item)

    or return an async generator from a helper::

        def fetch(self, since=None) -> AsyncIterator[Document]:
            return self._gen(since)

        async def _gen(self, since):
            ...
            yield doc

    Both patterns are consumed by the scheduler with ``async for doc in connector.fetch(since):``.
    """

    name: ClassVar[str]

    @abstractmethod
    async def authenticate(self) -> bool:
        """Verify/refresh credentials.  Return False if auth is invalid."""
        ...

    @abstractmethod
    def fetch(self, since: datetime.datetime | None = None) -> AsyncIterator[Document]:
        """Return an async iterator of documents updated since *since* (or all if None).

        Declared as a plain ``def`` so implementations can be either async
        generators (``async def fetch(self, ...): yield doc``) or regular
        methods returning an async iterator — without requiring the caller
        to ``await`` the method before iterating.
        """
        ...

    @abstractmethod
    async def health_check(self) -> ConnectorStatus:
        """Return current health and statistics for this connector."""
        ...

    @abstractmethod
    async def get_sync_state(self) -> SyncState:
        """Return the persisted sync checkpoint for incremental fetching.

        Async to support implementations that read from a database or file.
        """
        ...

    @abstractmethod
    async def restore_sync_state(self, state: SyncState) -> None:
        """Persist a new sync checkpoint after a successful run.

        Async to support implementations that write to a database or file.
        """
        ...
