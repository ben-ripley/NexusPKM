"""ConnectorRegistry — maintains the set of registered connectors and their statuses.

Spec: ADR-004
"""

from __future__ import annotations

import structlog

from nexuspkm.connectors.base import BaseConnector, ConnectorStatus

log = structlog.get_logger(__name__)


class ConnectorRegistry:
    """Registry for connector instances and their statuses.

    Not thread-safe.  Intended for use exclusively within a single asyncio
    event loop; all callers (FastAPI request handlers and APScheduler async
    jobs) share the same loop and therefore never mutate the registry
    concurrently.
    """

    def __init__(self) -> None:
        self._connectors: dict[str, BaseConnector] = {}
        self._statuses: dict[str, ConnectorStatus] = {}

    def register(self, connector: BaseConnector) -> None:
        """Add a connector to the registry and initialise it as unavailable."""
        self._connectors[connector.name] = connector
        self._statuses[connector.name] = ConnectorStatus(name=connector.name, status="unavailable")
        log.info("connector_registered", connector=connector.name)

    def get(self, name: str) -> BaseConnector | None:
        """Return the connector with *name*, or None if not registered."""
        return self._connectors.get(name)

    def all_connectors(self) -> list[BaseConnector]:
        """Return all registered connectors."""
        return list(self._connectors.values())

    def update_status(self, name: str, status: ConnectorStatus) -> None:
        """Overwrite the stored status for *name*.  No-op for unknown names."""
        if name not in self._connectors:
            return
        self._statuses[name] = status

    def get_all_statuses(self) -> dict[str, ConnectorStatus]:
        """Return a snapshot of all connector statuses."""
        return dict(self._statuses)
