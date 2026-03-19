"""Connector plugin system — abstract base, registry, and sync scheduler.

Spec: ADR-004
"""

from nexuspkm.connectors.base import BaseConnector, ConnectorStatus
from nexuspkm.connectors.registry import ConnectorRegistry
from nexuspkm.connectors.scheduler import SyncScheduler

__all__ = [
    "BaseConnector",
    "ConnectorRegistry",
    "ConnectorStatus",
    "SyncScheduler",
]
