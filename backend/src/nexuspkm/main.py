import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from nexuspkm.api.apple_notes import router as apple_notes_router
from nexuspkm.api.chat import get_chat_service
from nexuspkm.api.chat import router as chat_router
from nexuspkm.api.connectors import generic_router as generic_connectors_router
from nexuspkm.api.connectors import get_connector_registry, get_sync_scheduler
from nexuspkm.api.connectors import router as connectors_router
from nexuspkm.api.dashboard import router as dashboard_router
from nexuspkm.api.engine import get_knowledge_index
from nexuspkm.api.engine import router as engine_router
from nexuspkm.api.entities import (
    get_contradiction_detector,
    get_extraction_queue,
    get_graph_store,
)
from nexuspkm.api.entities import router as entities_router
from nexuspkm.api.jira import router as jira_router
from nexuspkm.api.obsidian import router as obsidian_router
from nexuspkm.api.outlook import router as outlook_router
from nexuspkm.api.providers import get_registry
from nexuspkm.api.providers import router as providers_router
from nexuspkm.api.schedule import get_schedule_service
from nexuspkm.api.schedule import router as schedule_router
from nexuspkm.api.search import get_graph_store as search_get_graph_store
from nexuspkm.api.search import get_obsidian_vault_path as search_get_obsidian_vault_path
from nexuspkm.api.search import router as search_router
from nexuspkm.config.loader import load_config
from nexuspkm.connectors.registry import ConnectorRegistry
from nexuspkm.connectors.scheduler import SyncScheduler
from nexuspkm.engine import (
    ContradictionDetector,
    EntityDeduplicator,
    EntityExtractionPipeline,
    EntityExtractor,
    ExtractionQueue,
    GraphStore,
    HybridRetriever,
    KnowledgeIndex,
    VectorStore,
)
from nexuspkm.providers.registry import ProviderRegistry
from nexuspkm.services.chat import ChatService
from nexuspkm.services.schedule import ScheduleService

log = structlog.get_logger()

_registry: ProviderRegistry | None = None
_knowledge_index: KnowledgeIndex | None = None
_vector_store: VectorStore | None = None
_graph_store: GraphStore | None = None
_connector_registry: ConnectorRegistry | None = None
_sync_scheduler: SyncScheduler | None = None
_extraction_queue: ExtractionQueue | None = None
_contradiction_detector: ContradictionDetector | None = None
_chat_service: ChatService | None = None
_schedule_service: ScheduleService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _registry, _knowledge_index, _vector_store, _graph_store
    global _connector_registry, _sync_scheduler, _extraction_queue, _contradiction_detector
    global _chat_service, _schedule_service
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
        # Init extraction queue (persistent SQLite) before KnowledgeIndex so the
        # queue can be passed in for automatic enqueuing after each ingest.
        extraction_db_path = data_dir / "extraction_queue.db"
        _extraction_queue = ExtractionQueue(extraction_db_path)
        await _extraction_queue.init()
        contradiction_db_path = data_dir / "contradictions.db"
        _contradiction_detector = ContradictionDetector(contradiction_db_path)
        await _contradiction_detector.init()
        _knowledge_index = KnowledgeIndex(
            _vector_store,
            _graph_store,
            embedding_provider,
            extraction_queue=_extraction_queue,
        )
    except Exception:
        if _graph_store is not None:
            await asyncio.to_thread(_graph_store.close)
        await _vector_store.close()
        raise
    app.dependency_overrides[get_knowledge_index] = lambda: _knowledge_index
    app.dependency_overrides[get_graph_store] = lambda: _graph_store
    app.dependency_overrides[get_extraction_queue] = lambda: _extraction_queue
    app.dependency_overrides[get_contradiction_detector] = lambda: _contradiction_detector
    app.dependency_overrides[search_get_graph_store] = lambda: _graph_store
    _schedule_service = ScheduleService(_graph_store)
    app.dependency_overrides[get_schedule_service] = lambda: _schedule_service

    llm_provider = _registry.get_llm()
    _extractor = EntityExtractor(llm_provider)
    _deduplicator = EntityDeduplicator(
        _graph_store,
        _knowledge_index.graph_lock,
        llm_provider,
    )
    _pipeline = EntityExtractionPipeline(
        _extractor,
        _deduplicator,
        _graph_store,
        _knowledge_index.graph_lock,
        _contradiction_detector,
    )
    _extraction_queue.start(_pipeline, concurrency=2)

    _retriever = HybridRetriever(
        _vector_store,
        _graph_store,
        embedding_provider,
        graph_lock=_knowledge_index.graph_lock,
    )
    _chat_service = ChatService(_retriever, llm_provider, data_dir / "chat.db")
    await _chat_service.init()
    app.dependency_overrides[get_chat_service] = lambda: _chat_service

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

    if config.connectors.outlook.enabled:
        from nexuspkm.connectors.ms_graph.outlook import OutlookConnector

        outlook_connector = OutlookConnector(
            token_dir=data_dir / ".tokens",
            state_dir=data_dir / "connectors",
            config=config.connectors.outlook,
        )
        _connector_registry.register(outlook_connector)
        intervals["outlook"] = config.connectors.outlook.sync_interval_minutes * 60
        log.info("outlook_connector_registered")

    if config.connectors.jira.enabled:
        from nexuspkm.connectors.jira.connector import JiraConnector

        _jira_connector = JiraConnector(
            state_dir=data_dir / "connectors",
            config=config.connectors.jira,
        )
        _connector_registry.register(_jira_connector)
        intervals["jira"] = config.connectors.jira.sync_interval_minutes * 60
        log.info("jira_connector_registered")

    if config.connectors.apple_notes.enabled:
        from nexuspkm.connectors.apple_notes.connector import AppleNotesConnector

        _apple_notes_connector = AppleNotesConnector(
            state_dir=data_dir / "connectors",
            config=config.connectors.apple_notes,
        )
        _connector_registry.register(_apple_notes_connector)
        intervals["apple_notes"] = config.connectors.apple_notes.sync_interval_minutes * 60
        log.info("apple_notes_connector_registered")

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
        _vault = _obsidian_connector.vault_path
        app.dependency_overrides[search_get_obsidian_vault_path] = lambda: _vault
        log.info("obsidian_connector_registered")

    # Run startup health checks so the UI shows real status before the first
    # scheduled sync fires.
    for connector in _connector_registry.all_connectors():
        try:
            initial_status = await connector.health_check()
            _connector_registry.update_status(connector.name, initial_status)
        except Exception as exc:  # pragma: no cover
            log.warning(
                "connector_startup_health_check_failed",
                connector=connector.name,
                error=str(exc),
            )

    _sync_scheduler = SyncScheduler(_connector_registry, _knowledge_index)
    app.dependency_overrides[get_connector_registry] = lambda: _connector_registry
    app.dependency_overrides[get_sync_scheduler] = lambda: _sync_scheduler

    from nexuspkm.api.apple_notes import (
        get_connector_registry as an_get_registry,
    )
    from nexuspkm.api.apple_notes import (
        get_sync_scheduler as an_get_scheduler,
    )
    from nexuspkm.api.jira import (
        get_connector_registry as jira_get_registry,
    )
    from nexuspkm.api.jira import (
        get_sync_scheduler as jira_get_scheduler,
    )
    from nexuspkm.api.obsidian import (
        get_connector_registry as obs_get_registry,
    )
    from nexuspkm.api.obsidian import (
        get_sync_scheduler as obs_get_scheduler,
    )
    from nexuspkm.api.outlook import (
        get_connector_registry as outlook_get_registry,
    )
    from nexuspkm.api.outlook import (
        get_sync_scheduler as outlook_get_scheduler,
    )

    app.dependency_overrides[an_get_registry] = lambda: _connector_registry
    app.dependency_overrides[an_get_scheduler] = lambda: _sync_scheduler
    app.dependency_overrides[obs_get_registry] = lambda: _connector_registry
    app.dependency_overrides[obs_get_scheduler] = lambda: _sync_scheduler
    app.dependency_overrides[outlook_get_registry] = lambda: _connector_registry
    app.dependency_overrides[outlook_get_scheduler] = lambda: _sync_scheduler
    app.dependency_overrides[jira_get_registry] = lambda: _connector_registry
    app.dependency_overrides[jira_get_scheduler] = lambda: _sync_scheduler
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
    if _extraction_queue is not None:
        await _extraction_queue.stop()
    if _chat_service is not None:
        await _chat_service.close()
    if _vector_store:
        await _vector_store.close()
    if _graph_store:
        await asyncio.to_thread(_graph_store.close)
    _chat_service = None
    _schedule_service = None
    _registry = None
    _knowledge_index = None
    _vector_store = None
    _graph_store = None
    _connector_registry = None
    _sync_scheduler = None
    _extraction_queue = None
    _contradiction_detector = None


app = FastAPI(title="NexusPKM", lifespan=lifespan)
app.include_router(providers_router)
app.include_router(engine_router)
app.include_router(connectors_router)
app.include_router(apple_notes_router)
app.include_router(jira_router)
app.include_router(outlook_router)
app.include_router(obsidian_router)
app.include_router(generic_connectors_router)
app.include_router(entities_router)
app.include_router(chat_router)
app.include_router(schedule_router)
app.include_router(search_router)
app.include_router(dashboard_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
