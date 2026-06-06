from fastapi import APIRouter, Depends, Header, Query
from shared_schemas import AppSettings, FeedbackRequest, FeedbackResponse, UserContext

from rag_api.dependencies import (
    RequestAuthContext,
    effective_user_context,
    get_feedback_service,
    get_request_auth_context,
    get_runtime_settings,
)
from rag_api.services import FeedbackService

router = APIRouter(prefix="/api/v1", tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse)
async def create_feedback(
    request: FeedbackRequest,
    x_user_id: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_acl_tags: str | None = Header(default=None),
    auth_context: RequestAuthContext = Depends(get_request_auth_context),
    settings: AppSettings = Depends(get_runtime_settings),
    service: FeedbackService = Depends(get_feedback_service),
) -> FeedbackResponse:
    user_context = _user_context(auth_context, settings, x_user_id, x_user_email, x_tenant_id, x_acl_tags)
    return service.create(request, user_context)


@router.get("/feedback", response_model=list[FeedbackResponse])
async def list_feedback(
    limit: int = Query(default=50, ge=1, le=100),
    x_user_id: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_acl_tags: str | None = Header(default=None),
    auth_context: RequestAuthContext = Depends(get_request_auth_context),
    settings: AppSettings = Depends(get_runtime_settings),
    service: FeedbackService = Depends(get_feedback_service),
) -> list[FeedbackResponse]:
    user_context = _user_context(auth_context, settings, x_user_id, x_user_email, x_tenant_id, x_acl_tags)
    return service.list_for_user(user_context, limit=limit)


def _user_context(
    auth_context: RequestAuthContext,
    settings: AppSettings,
    x_user_id: str | None,
    x_user_email: str | None,
    x_tenant_id: str | None,
    x_acl_tags: str | None,
) -> UserContext:
    return effective_user_context(
        auth_context=auth_context,
        settings=settings,
        x_user_id=x_user_id,
        x_user_email=x_user_email,
        x_tenant_id=x_tenant_id,
        x_acl_tags=x_acl_tags,
    )

