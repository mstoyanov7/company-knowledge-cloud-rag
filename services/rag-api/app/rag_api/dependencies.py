from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status
from shared_schemas import AppSettings, UserContext

from rag_api.adapters import MockLlmAdapter, MockRetriever, QdrantAclRetriever
from rag_api.ports import RetrievalPort
from rag_api.services import (
    AccessScopeResolver,
    AnswerService,
    AuthenticationService,
    ClaimsToScopeMapper,
    GraphWebhookService,
    KeywordOverlapReranker,
    OidcTokenValidator,
    PromptBuilder,
    SecurityAuditLogger,
    SystemService,
    TokenValidationError,
)
from sync_worker.persistence import PostgresOpsStore


@dataclass(slots=True)
class RequestAuthContext:
    user_context: UserContext | None = None
    auth_method: str = "anonymous"


def get_runtime_settings(request: Request) -> AppSettings:
    return request.app.state.settings


def get_retriever(settings: AppSettings) -> RetrievalPort:
    if settings.retrieval_provider == "qdrant":
        return QdrantAclRetriever(settings)
    return MockRetriever(settings)


def get_answer_service(settings: AppSettings = Depends(get_runtime_settings)) -> AnswerService:
    reranker = KeywordOverlapReranker() if settings.rerank_enabled else None
    return AnswerService(
        llm=MockLlmAdapter(model_name=settings.default_model_name),
        prompt_builder=PromptBuilder(),
        retriever=get_retriever(settings),
        access_scope_resolver=AccessScopeResolver(),
        reranker=reranker,
        retrieval_candidate_multiplier=settings.retrieval_candidate_multiplier,
        audit_logger=get_security_audit_logger(settings),
    )


def get_system_service(settings: AppSettings = Depends(get_runtime_settings)) -> SystemService:
    return SystemService(
        llm=MockLlmAdapter(model_name=settings.default_model_name),
        retriever=get_retriever(settings),
        settings=settings,
    )


def get_graph_webhook_service(settings: AppSettings = Depends(get_runtime_settings)) -> GraphWebhookService:
    return GraphWebhookService(
        settings=settings,
        store=PostgresOpsStore(settings),
    )


def get_security_audit_logger(settings: AppSettings = Depends(get_runtime_settings)) -> SecurityAuditLogger:
    return SecurityAuditLogger(settings, store=PostgresOpsStore(settings))


def get_authentication_service(settings: AppSettings = Depends(get_runtime_settings)) -> AuthenticationService:
    return AuthenticationService(
        settings=settings,
        validator=OidcTokenValidator(settings),
        mapper=ClaimsToScopeMapper(settings),
        audit=get_security_audit_logger(settings),
    )


def get_request_auth_context(
    authorization: str | None = Header(default=None),
    x_rag_api_key: str | None = Header(default=None),
    settings: AppSettings = Depends(get_runtime_settings),
    auth_service: AuthenticationService = Depends(get_authentication_service),
) -> RequestAuthContext:
    expected_api_key = settings.rag_api_key.get_secret_value()
    bearer_token = _bearer_token(authorization)

    if expected_api_key and (x_rag_api_key == expected_api_key or bearer_token == expected_api_key):
        auth_service.audit.record("authentication", "success", metadata={"method": "api_key"})
        return RequestAuthContext(auth_method="api_key")

    if settings.auth_enabled and bearer_token:
        try:
            principal = auth_service.authenticate_bearer_token(bearer_token)
            return RequestAuthContext(user_context=principal.user_context, auth_method="oidc")
        except TokenValidationError as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error

    if expected_api_key or settings.auth_required:
        auth_service.audit.record(
            "authorization",
            "failure",
            metadata={"reason": "missing_or_invalid_api_key_or_bearer_token"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key or bearer token.",
        )

    return RequestAuthContext(auth_method="anonymous")


def verify_rag_api_key(
    authorization: str | None = Header(default=None),
    x_rag_api_key: str | None = Header(default=None),
    settings: AppSettings = Depends(get_runtime_settings),
) -> None:
    expected = settings.rag_api_key.get_secret_value()
    if not expected:
        return

    if x_rag_api_key == expected:
        return

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", maxsplit=1)[1]
        if token == expected:
            return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid RAG API key.",
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


def _bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", maxsplit=1)[1]
    return None
