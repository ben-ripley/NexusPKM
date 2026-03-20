import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from nexuspkm.api.connectors import generic_router as generic_connectors_router
from nexuspkm.api.connectors import get_connector_registry, get_sync_scheduler
from nexuspkm.api.connectors import router as connectors_router
from nexuspkm.api.engine import get_knowledge_index
from nexuspkm.api.engine import router as engine_router
from nexuspkm.api.obsidian import router as obsidian_router
from nexuspkm.api.providers import get_registry
from nexuspkm.api.providers import router as providers_router
from nexuspkm.config.loader import load_config
from nexuspkm.connectors.registry import ConnectorRegistry
from nexuspkm.connectors.scheduler import SyncScheduler
from nexuspkm.engine import GraphStore, KnowledgeIndex, VectorStore
from nexuspkm.providers.registry import ProviderRegistry

log = structlog.get_logger()

_registry: ProviderRegistry | None = None
_knowledge_index: KnowledgeIndex | None = None
_vector_store: VectorStore | None = None
_graph_store: GraphStore | None = None
_connector_registry: ConnectorRegistry | None = None
_sync_scheduler: SyncScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _registry, _knowledge_index, _vector_store, _graph_store
    global _connector_registry, _sync_scheduler
    config = await asyncio.to_thread(load_config)
    _registry = ProviderRegistry(config.providers)
    app.dependency_overrides[get_registry] = lambda: _registry

    data_dir = config.app.data.dir
    embed_dim = config.providers.embedding.primary.dimensions
    embedding_provider = _registry.get_embedding()
    # VectorStore.__init__ is lazy (no disk I/O); GraphStore.__init__ opens the
    # Kuzu database and runs schema DDL, so it must be offloaded to a thread.
    _vector_store = VectorStore(db_path=str(data_dir / "lancedb"), dimensions=embed_dim)
    try:
        _graph_store = await asyncio.to_thread(GraphStore, data_dir / "kuzu")
        _knowledge_index = KnowledgeIndex(_vector_store, _graph_store, embedding_provider)
    except Exception:
        if _graph_store is not None:
            await asyncio.to_thread(_graph_store.close)
        await _vector_store.close()
        raise
    app.dependency_overrides[get_knowledge_index] = lambda: _knowledge_index

    _connector_registry = ConnectorRegistry()
    intervals: dict[str, int] = {}

    if config.connectors.teams.enabled:
        from nexuspkm.connectors.ms_graph.teams import TeamsTranscriptConnector

        teams_connector = TeamsTranscriptConnector(
            token_dir=data_dir / ".tokens",
            state_dir=data_dir / "connectors",
            config=config.connectors.teams,
        )
        _connector_registry.register(teams_connector)
        intervals["teams"] = config.connectors.teams.sync_interval_minutes * 60
        log.info("teams_connector_registered")

    _obsidian_connector = None
    if config.connectors.obsidian.enabled and config.connectors.obsidian.vault_path:
        from nexuspkm.connectors.obsidian.connector import ObsidianNotesConnector

        _obsidian_connector = ObsidianNotesConnector(
            vault_path=config.connectors.obsidian.vault_path,
            state_dir=data_dir / "connectors",
            config=config.connectors.obsidian,
        )
        _connector_registry.register(_obsidian_connector)
        intervals["obsidian"] = config.connectors.obsidian.sync_interval_minutes * 60
        log.info("obsidian_connector_registered")

    _sync_scheduler = SyncScheduler(_connector_registry, _knowledge_index)
    app.dependency_overrides[get_connector_registry] = lambda: _connector_registry
    app.dependency_overrides[get_sync_scheduler] = lambda: _sync_scheduler

    from nexuspkm.api.obsidian import (
        get_connector_registry as obs_get_registry,
    )
    from nexuspkm.api.obsidian import (
        get_sync_scheduler as obs_get_scheduler,
    )

    app.dependency_overrides[obs_get_registry] = lambda: _connector_registry
    app.dependency_overrides[obs_get_scheduler] = lambda: _sync_scheduler
    _sync_scheduler.start(intervals)

    if _obsidian_connector is not None and _knowledge_index is not None:
        await _obsidian_connector.start_watching(
            on_upsert=_knowledge_index.insert,
            on_delete=_knowledge_index.delete,
        )

    log.info(
        "nexuspkm_started",
        llm_provider=config.providers.llm.primary.provider,
        embedding_provider=config.providers.embedding.primary.provider,
    )
    yield

    if _obsidian_connector is not None:
        await _obsidian_connector.stop_watching()
    if _sync_scheduler:
        await _sync_scheduler.shutdown()
    if _vector_store:
        await _vector_store.close()
    if _graph_store:
        await asyncio.to_thread(_graph_store.close)
    _registry = None
    _knowledge_index = None
    _vector_store = None
    _graph_store = None
    _connector_registry = None
    _sync_scheduler = None


app = FastAPI(title="NexusPKM", lifespan=lifespan)
app.include_router(providers_router)
app.include_router(engine_router)
app.include_router(connectors_router)
app.include_router(obsidian_router)
app.include_router(generic_connectors_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
