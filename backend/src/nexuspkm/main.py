from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from nexuspkm.api.providers import get_registry
from nexuspkm.api.providers import router as providers_router
from nexuspkm.config.loader import load_config
from nexuspkm.providers.registry import ProviderRegistry

log = structlog.get_logger()

_registry: ProviderRegistry | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _registry
    config = load_config()
    _registry = ProviderRegistry(config.providers)
    app.dependency_overrides[get_registry] = lambda: _registry
    log.info(
        "nexuspkm_started",
        llm_provider=config.providers.llm.primary.provider,
        embedding_provider=config.providers.embedding.primary.provider,
    )
    yield
    _registry = None


app = FastAPI(title="NexusPKM", lifespan=lifespan)
app.include_router(providers_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
