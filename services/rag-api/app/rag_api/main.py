import logging

import uvicorn
from fastapi import FastAPI
from shared_schemas import AppSettings, get_settings

from rag_api.api import (
    admin_router,
    answer_router,
    auth_router,
    documents_router,
    feedback_router,
    openai_compat_router,
    system_router,
    topics_router,
)
from rag_api.observability import configure_observability
from rag_api.persistence import AppDataStore
from rag_api.services.local_auth import LocalAuthService
from rag_api.services.topic_loader import TopicLoader
from rag_api.services.topic_service import TopicService


def create_app(settings: AppSettings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    application = FastAPI(
        title="Cloud RAG API",
        version=resolved_settings.app_version,
        description="Local proof-of-concept backend for enterprise onboarding RAG.",
    )
    application.state.settings = resolved_settings
    app_data_store = AppDataStore(resolved_settings)
    app_data_store.ensure_schema()
    LocalAuthService(settings=resolved_settings, store=app_data_store).bootstrap_admin()
    TopicService(loader=TopicLoader(resolved_settings.topics_config_path), store=app_data_store)
    application.state.app_data_store = app_data_store
    configure_observability(application, resolved_settings, default_service_name="rag-api")
    application.include_router(system_router)
    application.include_router(auth_router)
    application.include_router(admin_router)
    application.include_router(topics_router)
    application.include_router(documents_router)
    application.include_router(feedback_router)
    application.include_router(answer_router)
    application.include_router(openai_compat_router)
    return application


def run() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    uvicorn.run(
        "rag_api.main:create_app",
        factory=True,
        host=settings.rag_api_host,
        port=settings.rag_api_port,
        reload=False,
    )


app = create_app()
