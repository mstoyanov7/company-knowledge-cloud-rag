from fastapi import APIRouter, Depends, Header

from rag_api.dependencies import RequestAuthContext, get_answer_service, get_request_auth_context
from rag_api.services import AnswerService
from shared_schemas import AnswerRequest, AnswerResponse

router = APIRouter(prefix="/api/v1", tags=["answer"])


@router.post("/answer", response_model=AnswerResponse)
async def answer(
    request: AnswerRequest,
    x_user_id: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_acl_tags: str | None = Header(default=None),
    auth_context: RequestAuthContext = Depends(get_request_auth_context),
    service: AnswerService = Depends(get_answer_service),
) -> AnswerResponse:
    if auth_context.user_context is not None:
        request = request.model_copy(update={"user_context": auth_context.user_context})
    elif any([x_user_id, x_user_email, x_tenant_id, x_acl_tags]):
        user_context = request.user_context.model_copy(
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
        request = request.model_copy(update={"user_context": user_context})
    return await service.answer(request)


def _parse_header_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
