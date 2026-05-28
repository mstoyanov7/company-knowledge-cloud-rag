from fastapi import APIRouter, Depends, Header

from rag_api.dependencies import RequestAuthContext, get_request_auth_context, get_topic_service
from rag_api.services import TopicService
from shared_schemas import Topic, UserContext

router = APIRouter(prefix="/api/v1", tags=["topics"])


@router.get("/topics", response_model=list[Topic])
async def list_topics(
    x_acl_tags: str | None = Header(default=None),
    auth_context: RequestAuthContext = Depends(get_request_auth_context),
    service: TopicService = Depends(get_topic_service),
) -> list[Topic]:
    user_context = auth_context.user_context
    if user_context is None and x_acl_tags is not None:
        user_context = UserContext(acl_tags=_parse_header_list(x_acl_tags))
    return service.list_topics(user_context)


def _parse_header_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
