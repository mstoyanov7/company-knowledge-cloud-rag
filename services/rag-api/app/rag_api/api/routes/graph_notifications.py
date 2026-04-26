from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import ValidationError
from shared_schemas import GraphNotificationEnvelope, GraphWebhookAccepted

from rag_api.dependencies import get_graph_webhook_service
from rag_api.services import GraphWebhookService, InvalidGraphNotificationError

router = APIRouter(prefix="/api/v1/graph", tags=["graph-notifications"])


@router.post("/notifications", response_model=GraphWebhookAccepted, status_code=status.HTTP_202_ACCEPTED)
async def graph_notifications(
    request: Request,
    validation_token: str | None = Query(default=None, alias="validationToken"),
    service: GraphWebhookService = Depends(get_graph_webhook_service),
) -> GraphWebhookAccepted | PlainTextResponse:
    return await _handle_graph_webhook(request, validation_token, service)


@router.post("/lifecycle", response_model=GraphWebhookAccepted, status_code=status.HTTP_202_ACCEPTED)
async def graph_lifecycle_notifications(
    request: Request,
    validation_token: str | None = Query(default=None, alias="validationToken"),
    service: GraphWebhookService = Depends(get_graph_webhook_service),
) -> GraphWebhookAccepted | PlainTextResponse:
    return await _handle_graph_webhook(request, validation_token, service)


async def _handle_graph_webhook(
    request: Request,
    validation_token: str | None,
    service: GraphWebhookService,
) -> GraphWebhookAccepted | PlainTextResponse:
    if validation_token is not None:
        return PlainTextResponse(
            content=unquote(validation_token),
            status_code=status.HTTP_200_OK,
            media_type="text/plain",
        )

    try:
        payload = await request.json()
        envelope = GraphNotificationEnvelope.model_validate(payload)
        return service.accept(envelope)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Microsoft Graph notification payload: {error}",
        ) from error
    except InvalidGraphNotificationError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
