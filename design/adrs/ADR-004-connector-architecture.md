# ADR-004: Connector Architecture

**Status:** Accepted
**Date:** 2026-03-16
**Deciders:** Project Team

## Context

NexusPKM ingests data from multiple heterogeneous sources (Teams, Outlook, Obsidian, JIRA, Apple Notes) with more expected in the future. Each source has different:
- Authentication mechanisms (OAuth2, API tokens, filesystem access)
- Data formats (VTT transcripts, markdown, HTML, JSON)
- Sync patterns (webhooks, polling, filesystem watching)
- Rate limits and pagination strategies

We need a pluggable architecture that allows adding new connectors without modifying the core ingestion pipeline.

## Decision

Implement a **plugin-based connector system** with the following design:

### BaseConnector Abstract Class

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator
from nexuspkm.models.document import Document, SyncState

class BaseConnector(ABC):
    """Base class for all data source connectors."""

    @abstractmethod
    async def authenticate(self) -> bool:
        """Validate credentials and establish connection."""

    @abstractmethod
    async def fetch(self, since: datetime | None = None) -> AsyncIterator[Document]:
        """Fetch documents, optionally since a given timestamp for incremental sync."""

    @abstractmethod
    async def health_check(self) -> ConnectorStatus:
        """Check connectivity and report status."""

    @abstractmethod
    def get_sync_state(self) -> SyncState:
        """Return current sync state for persistence."""

    @abstractmethod
    def restore_sync_state(self, state: SyncState) -> None:
        """Restore sync state from persistence."""
```

### Key Design Principles

1. **Common Document schema**: all connectors transform source data into a unified `Document` model with standardized metadata (source type, timestamp, sync ID, raw content, extracted text)
2. **Incremental sync**: every connector tracks its sync state and supports fetching only new/changed data
3. **Configuration-driven registration**: connectors are registered via `config/connectors.yaml`, not hard-coded
4. **Async-first**: all connectors use async I/O for non-blocking operation
5. **Isolation**: connector failures do not affect other connectors or the core pipeline
6. **Rate limiting**: each connector manages its own rate limiting appropriate to the source API

### Connector Configuration Example

```yaml
connectors:
  teams:
    enabled: true
    type: microsoft_teams
    sync_interval: 3600  # seconds
    settings:
      tenant_id: ${MS_TENANT_ID}
      client_id: ${MS_CLIENT_ID}

  obsidian:
    enabled: true
    type: obsidian
    sync_interval: 300
    settings:
      vault_path: /Users/bripley/ObsidianVault
      exclude_patterns:
        - ".trash/**"
        - ".obsidian/**"
```

### Connector Lifecycle

1. **Registration**: on startup, read connector configs and instantiate enabled connectors
2. **Authentication**: call `authenticate()` on each connector
3. **Initial sync**: full fetch on first run (no `since` parameter)
4. **Incremental sync**: scheduled fetches with `since` parameter based on stored sync state
5. **Health monitoring**: periodic `health_check()` calls, status exposed via API

## Consequences

### Positive
- New connectors require only implementing the `BaseConnector` interface and adding a config block
- Connectors are isolated — one failing connector doesn't affect others
- Incremental sync reduces API calls and processing overhead
- Async design prevents slow connectors from blocking the pipeline
- Configuration-driven enablement allows toggling connectors without code changes

### Negative
- Each connector is a significant implementation effort (auth, pagination, error handling, transform)
- The common Document schema may lose source-specific nuances
- Sync state persistence adds complexity
- Testing requires mocking each source's API

### Risks
- Microsoft Graph API changes could break Teams/Outlook connectors — pin API versions
- Apple Notes has no official API — the SQLite/AppleScript approach is fragile across macOS updates
