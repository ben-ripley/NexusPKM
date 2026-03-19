import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from nexuspkm.api.engine import get_knowledge_index
from nexuspkm.api.engine import router as engine_router
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
    # No connectors registered yet — concrete connectors added in future NXP issues.
    intervals: dict[str, int] = {}
    _sync_scheduler = SyncScheduler(_connector_registry, _knowledge_index)
    _sync_scheduler.start(intervals)

    log.info(
        "nexuspkm_started",
        llm_provider=config.providers.llm.primary.provider,
        embedding_provider=config.providers.embedding.primary.provider,
    )
    yield

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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
