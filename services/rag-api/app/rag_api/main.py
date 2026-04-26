import logging

import uvicorn
from fastapi import FastAPI
from shared_schemas import AppSettings, get_settings

from rag_api.api import answer_router, graph_notifications_router, openai_compat_router, system_router
from rag_api.observability import configure_observability


def create_app(settings: AppSettings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    application = FastAPI(
        title="Cloud RAG API",
        version=resolved_settings.app_version,
        description="Local proof-of-concept backend for enterprise onboarding RAG.",
    )
    application.state.settings = resolved_settings
    configure_observability(application, resolved_settings, default_service_name="rag-api")
    application.include_router(system_router)
    application.include_router(answer_router)
    application.include_router(graph_notifications_router)
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
