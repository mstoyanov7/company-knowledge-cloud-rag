import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from rag_api.api.openai_models import (
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ModelCard,
    ModelListResponse,
)
from rag_api.dependencies import get_answer_service, get_runtime_settings, verify_openai_api_key
from rag_api.services import AnswerService
from shared_schemas import AnswerRequest, AppSettings, UserContext

router = APIRouter(prefix="/v1", tags=["openai-compatible"], dependencies=[Depends(verify_openai_api_key)])


@router.get("/models", response_model=ModelListResponse)
async def list_models(service: AnswerService = Depends(get_answer_service)) -> ModelListResponse:
    model_name = service.llm.model_name
    return ModelListResponse(data=[ModelCard(id=model_name)])


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def create_chat_completion(
    request: ChatCompletionRequest,
    service: AnswerService = Depends(get_answer_service),
    settings: AppSettings = Depends(get_runtime_settings),
) -> ChatCompletionResponse | StreamingResponse:
    user_message = next((message.content for message in reversed(request.messages) if message.role == "user"), None)
    if not user_message:
        raise HTTPException(
            status_code=400,
            detail="At least one user message is required.",
        )

    user_context = UserContext(acl_tags=settings.auth_default_acl_tag_list)
    answer_response = await service.answer(AnswerRequest(question=user_message, user_context=user_context))
    prompt_tokens = len(user_message.split())
    completion_tokens = len(answer_response.answer.split())
    model_name = request.model or answer_response.metadata.model

    if request.stream:
        async def event_stream() -> str:
            initial_chunk = {
                "id": answer_response.metadata.response_id,
                "object": "chat.completion.chunk",
                "created": int(answer_response.metadata.generated_at_utc.timestamp()),
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "content": answer_response.answer,
                        },
                        "finish_reason": None,
                    }
                ],
            }
            final_chunk = {
                "id": answer_response.metadata.response_id,
                "object": "chat.completion.chunk",
                "created": int(answer_response.metadata.generated_at_utc.timestamp()),
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }
                ],
            }
            yield f"data: {json.dumps(initial_chunk)}\n\n"
            yield f"data: {json.dumps(final_chunk)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return ChatCompletionResponse(
        model=model_name,
        choices=[
            ChatCompletionChoice(
                message=ChatCompletionMessage(content=answer_response.answer),
            )
        ],
        usage=ChatCompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
        citations=answer_response.citations,
    )
