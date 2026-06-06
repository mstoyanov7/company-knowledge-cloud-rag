import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from rag_api.dependencies import RequestAuthContext, effective_user_context, get_answer_service, get_query_log_service, get_request_auth_context, get_runtime_settings
from rag_api.services import AnswerService, QueryLogService, TopicNotFoundError
from shared_schemas import AnswerRequest, AnswerResponse, AppSettings

router = APIRouter(prefix="/api/v1", tags=["answer"])


@router.post("/answer", response_model=AnswerResponse)
async def answer(
    request: AnswerRequest,
    x_user_id: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_acl_tags: str | None = Header(default=None),
    auth_context: RequestAuthContext = Depends(get_request_auth_context),
    settings: AppSettings = Depends(get_runtime_settings),
    service: AnswerService = Depends(get_answer_service),
    query_log: QueryLogService = Depends(get_query_log_service),
) -> AnswerResponse:
    request = _request_with_effective_user_context(
        request,
        auth_context=auth_context,
        settings=settings,
        x_user_id=x_user_id,
        x_user_email=x_user_email,
        x_tenant_id=x_tenant_id,
        x_acl_tags=x_acl_tags,
    )
    try:
        response = await service.answer(request)
    except TopicNotFoundError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    query_log.record_question(question=request.question, topic_id=request.topic_id, user_context=request.user_context)
    return response


@router.post(
    "/answer/stream",
    response_model=AnswerResponse,
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def answer_stream(
    request: AnswerRequest,
    x_user_id: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_acl_tags: str | None = Header(default=None),
    auth_context: RequestAuthContext = Depends(get_request_auth_context),
    settings: AppSettings = Depends(get_runtime_settings),
    service: AnswerService = Depends(get_answer_service),
    query_log: QueryLogService = Depends(get_query_log_service),
) -> StreamingResponse:
    request = _request_with_effective_user_context(
        request,
        auth_context=auth_context,
        settings=settings,
        x_user_id=x_user_id,
        x_user_email=x_user_email,
        x_tenant_id=x_tenant_id,
        x_acl_tags=x_acl_tags,
    )

    async def events() -> AsyncIterator[str]:
        try:
            response = await service.answer(request)
        except TopicNotFoundError as error:
            yield _sse("error", {"detail": str(error)})
            return
        query_log.record_question(question=request.question, topic_id=request.topic_id, user_context=request.user_context)
        for chunk in _answer_chunks(response.answer):
            yield _sse("delta", {"text": chunk})
        yield _sse("final", response.model_dump(mode="json"))

    return StreamingResponse(events(), media_type="text/event-stream")


def _request_with_effective_user_context(
    request: AnswerRequest,
    *,
    auth_context: RequestAuthContext,
    settings: AppSettings,
    x_user_id: str | None,
    x_user_email: str | None,
    x_tenant_id: str | None,
    x_acl_tags: str | None,
) -> AnswerRequest:
    if auth_context.user_context is not None or any([x_user_id, x_user_email, x_tenant_id, x_acl_tags]):
        return request.model_copy(
            update={
                "user_context": effective_user_context(
                    auth_context=auth_context,
                    settings=settings,
                    x_user_id=x_user_id,
                    x_user_email=x_user_email,
                    x_tenant_id=x_tenant_id,
                    x_acl_tags=x_acl_tags,
                )
            }
        )
    if "user_context" not in request.model_fields_set and settings.auth_default_acl_tag_list:
        return request.model_copy(
            update={"user_context": request.user_context.model_copy(update={"acl_tags": settings.auth_default_acl_tag_list})}
        )
    return request


def _parse_header_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _answer_chunks(answer: str) -> list[str]:
    parts = answer.split(" ")
    chunks = []
    for index in range(0, len(parts), 8):
        chunk = " ".join(parts[index : index + 8])
        if index + 8 < len(parts):
            chunk += " "
        chunks.append(chunk)
    return chunks or [""]


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
