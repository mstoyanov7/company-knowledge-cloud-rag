from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status
from shared_schemas import AppSettings, UserContext

from rag_api.adapters import MockLlmAdapter, MockRetriever, OpenAICompatibleLlmAdapter, QdrantAclRetriever
from rag_api.adapters.source_metadata import MockSourceMetadataAdapter, PostgresSourceMetadataAdapter
from rag_api.persistence import AppDataStore
from rag_api.ports import DocumentMetadataPort, LlmPort, RetrievalPort
from rag_api.services import (
    AccessScopeResolver,
    AnswerService,
    AuthenticationService,
    ClaimsToScopeMapper,
    DocumentService,
    FeedbackService,
    KeywordOverlapReranker,
    OidcTokenValidator,
    PromptBuilder,
    QueryLogService,
    QueryPlanner,
    SecurityAuditLogger,
    SystemService,
    TopicLoader,
    TopicService,
    TokenValidationError,
)
from rag_api.services.local_auth import LocalAuthService


@dataclass(slots=True)
class RequestAuthContext:
    user_context: UserContext | None = None
    auth_method: str = "anonymous"


def get_runtime_settings(request: Request) -> AppSettings:
    return request.app.state.settings


def get_app_data_store(request: Request) -> AppDataStore:
    return request.app.state.app_data_store


def get_retriever(settings: AppSettings) -> RetrievalPort:
    if settings.retrieval_provider == "qdrant":
        return QdrantAclRetriever(settings)
    if settings.retrieval_provider == "semantic_fixture":
        from rag_api.adapters.retrieval.semantic_fixture import FixtureSemanticRetriever

        return FixtureSemanticRetriever(settings)
    return MockRetriever(settings)


def get_document_metadata(settings: AppSettings) -> DocumentMetadataPort:
    if settings.retrieval_provider == "qdrant":
        return PostgresSourceMetadataAdapter(settings)
    return MockSourceMetadataAdapter(settings)


def get_llm(settings: AppSettings, *, model_name: str | None = None) -> LlmPort:
    resolved_model = model_name or settings.default_model_name
    if settings.default_llm_provider.lower() in {"ollama", "openai-compatible", "openai_compatible"}:
        return OpenAICompatibleLlmAdapter(settings, model_name=resolved_model)
    return MockLlmAdapter(model_name=resolved_model)


def get_answer_service(
    settings: AppSettings = Depends(get_runtime_settings),
    store: AppDataStore | None = Depends(get_app_data_store),
) -> AnswerService:
    app_store = store if isinstance(store, AppDataStore) else None
    reranker = KeywordOverlapReranker() if settings.rerank_enabled else None
    llm = get_llm(settings, model_name=_runtime_llm_model(settings))
    from rag_api.services.retrieval_ranking import configure_semantic_scoring

    configure_semantic_scoring(getattr(settings, "retrieval_semantic_confident_score", 0.0))
    return AnswerService(
        llm=llm,
        prompt_builder=PromptBuilder(),
        retriever=get_retriever(settings),
        metadata=get_document_metadata(settings),
        access_scope_resolver=AccessScopeResolver(),
        reranker=reranker,
        retrieval_candidate_multiplier=settings.retrieval_candidate_multiplier,
        min_keyword_overlap=settings.retrieval_min_keyword_overlap,
        audit_logger=get_security_audit_logger(settings),
        query_planner=QueryPlanner(llm=llm),
        topic_service=get_topic_service(settings=settings, store=app_store),
        debug_enabled=settings.rag_debug_enabled,
        clarify_enabled=settings.clarify_enabled,
        clarify_closeness_ratio=settings.clarify_closeness_ratio,
        clarify_max_options=settings.clarify_max_options,
        guard_repair_enabled=settings.answer_guard_repair_enabled,
    )


def get_system_service(settings: AppSettings = Depends(get_runtime_settings)) -> SystemService:
    return SystemService(
        llm=get_llm(settings, model_name=_runtime_llm_model(settings)),
        retriever=get_retriever(settings),
        settings=settings,
    )


def get_topic_service(
    settings: AppSettings = Depends(get_runtime_settings),
    store: AppDataStore | None = Depends(get_app_data_store),
) -> TopicService:
    app_store = store if isinstance(store, AppDataStore) else None
    return TopicService(
        loader=TopicLoader(settings.topics_config_path),
        store=app_store,
        prune_orphaned_seed_topics=False,
    )


def get_document_service(settings: AppSettings = Depends(get_runtime_settings)) -> DocumentService:
    return DocumentService(
        metadata=get_document_metadata(settings),
        access_scope_resolver=AccessScopeResolver(),
    )


def get_query_log_service(store: AppDataStore = Depends(get_app_data_store)) -> QueryLogService:
    return QueryLogService(store=store)


def get_feedback_service(store: AppDataStore = Depends(get_app_data_store)) -> FeedbackService:
    return FeedbackService(store=store)


def get_local_auth_service(
    settings: AppSettings = Depends(get_runtime_settings),
    store: AppDataStore = Depends(get_app_data_store),
) -> LocalAuthService:
    return LocalAuthService(settings=settings, store=store)


def get_security_audit_logger(settings: AppSettings = Depends(get_runtime_settings)) -> SecurityAuditLogger:
    from sync_worker.persistence import PostgresOpsStore

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
    local_auth_service: LocalAuthService = Depends(get_local_auth_service),
) -> RequestAuthContext:
    expected_api_key = settings.rag_api_key.get_secret_value()
    bearer_token = _bearer_token(authorization)

    if bearer_token and bearer_token != expected_api_key:
        try:
            user_context, _profile = local_auth_service.authenticate_bearer_token(bearer_token)
            auth_service.audit.record(
                "authentication",
                "success",
                actor_user_id=user_context.user_id,
                tenant_id=user_context.tenant_id,
                metadata={"method": "session"},
            )
            return RequestAuthContext(user_context=user_context, auth_method="session")
        except TokenValidationError:
            if settings.auth_enabled:
                try:
                    principal = auth_service.authenticate_bearer_token(bearer_token)
                    return RequestAuthContext(user_context=principal.user_context, auth_method="oidc")
                except TokenValidationError as error:
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session token.")

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


def _runtime_llm_model(settings: AppSettings) -> str:
    try:
        from sync_worker.persistence import PostgresOpsStore

        return PostgresOpsStore(settings).get_system_runtime_settings().llm_model
    except Exception:
        return settings.default_model_name


def effective_user_context(
    *,
    auth_context: RequestAuthContext,
    settings: AppSettings,
    x_user_id: str | None = None,
    x_user_email: str | None = None,
    x_tenant_id: str | None = None,
    x_acl_tags: str | None = None,
) -> UserContext:
    if auth_context.user_context is not None:
        return auth_context.user_context
    user_context = UserContext()
    if any([x_user_id, x_user_email, x_tenant_id, x_acl_tags]):
        user_context = user_context.model_copy(
            update={
                key: value
                for key, value in {
                    "user_id": x_user_id,
                    "email": x_user_email,
                    "tenant_id": x_tenant_id,
                    "acl_tags": _parse_header_list(x_acl_tags) if x_acl_tags is not None else None,
                }.items()
                if value is not None
            }
        )
    elif settings.auth_default_acl_tag_list:
        user_context = user_context.model_copy(update={"acl_tags": settings.auth_default_acl_tag_list})
    return user_context


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


def _parse_header_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
