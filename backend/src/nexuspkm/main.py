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
from nexuspkm.engine import GraphStore, KnowledgeIndex, VectorStore
from nexuspkm.providers.registry import ProviderRegistry

log = structlog.get_logger()

_registry: ProviderRegistry | None = None
_knowledge_index: KnowledgeIndex | None = None
_vector_store: VectorStore | None = None
_graph_store: GraphStore | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _registry, _knowledge_index, _vector_store, _graph_store
    config = await asyncio.to_thread(load_config)
    _registry = ProviderRegistry(config.providers)
    app.dependency_overrides[get_registry] = lambda: _registry

    data_dir = config.app.data.dir
    embed_dim = config.providers.embedding.primary.dimensions
    embedding_provider = _registry.get_embedding()
    _vector_store = VectorStore(db_path=str(data_dir / "lancedb"), dimensions=embed_dim)
    _graph_store = GraphStore(db_path=data_dir / "kuzu")
    _knowledge_index = KnowledgeIndex(_vector_store, _graph_store, embedding_provider)
    app.dependency_overrides[get_knowledge_index] = lambda: _knowledge_index

    log.info(
        "nexuspkm_started",
        llm_provider=config.providers.llm.primary.provider,
        embedding_provider=config.providers.embedding.primary.provider,
    )
    yield

    if _vector_store:
        await _vector_store.close()
    if _graph_store:
        _graph_store.close()
    _registry = None
    _knowledge_index = None
    _vector_store = None
    _graph_store = None


app = FastAPI(title="NexusPKM", lifespan=lifespan)
app.include_router(providers_router)
app.include_router(engine_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
