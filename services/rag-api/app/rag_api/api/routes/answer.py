from fastapi import APIRouter, Depends

from rag_api.dependencies import get_answer_service
from rag_api.services import AnswerService
from shared_schemas import AnswerRequest, AnswerResponse

router = APIRouter(prefix="/api/v1", tags=["answer"])


@router.post("/answer", response_model=AnswerResponse)
async def answer(
    request: AnswerRequest,
    service: AnswerService = Depends(get_answer_service),
) -> AnswerResponse:
    return await service.answer(request)
