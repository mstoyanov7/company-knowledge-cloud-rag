from fastapi import Depends, Header, HTTPException, Request, status
from shared_schemas import AppSettings

from rag_api.adapters import MockLlmAdapter, MockRetriever
from rag_api.services import AnswerService, PromptBuilder, SystemService


def get_runtime_settings(request: Request) -> AppSettings:
    return request.app.state.settings


def get_answer_service(settings: AppSettings = Depends(get_runtime_settings)) -> AnswerService:
    return AnswerService(
        llm=MockLlmAdapter(model_name=settings.default_model_name),
        prompt_builder=PromptBuilder(),
        retriever=MockRetriever(settings),
    )


def get_system_service(settings: AppSettings = Depends(get_runtime_settings)) -> SystemService:
    return SystemService(
        llm=MockLlmAdapter(model_name=settings.default_model_name),
        retriever=MockRetriever(settings),
        settings=settings,
    )


def verify_openai_api_key(
    authorization: str | None = Header(default=None),
    settings: AppSettings = Depends(get_runtime_settings),
) -> None:
    expected = settings.mock_api_key.get_secret_value()
    if not expected:
        return

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token for OpenAI-compatible API.",
        )

    token = authorization.split(" ", maxsplit=1)[1]
    if token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key for OpenAI-compatible API.",
        )
