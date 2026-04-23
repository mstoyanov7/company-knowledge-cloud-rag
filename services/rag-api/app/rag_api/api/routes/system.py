from fastapi import APIRouter, Depends

from rag_api.dependencies import get_system_service
from rag_api.services import SystemService

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(service: SystemService = Depends(get_system_service)) -> dict[str, str]:
    return await service.health()


@router.get("/ready")
async def ready(service: SystemService = Depends(get_system_service)) -> dict[str, object]:
    return await service.ready()


@router.get("/version")
async def version(service: SystemService = Depends(get_system_service)) -> dict[str, str]:
    return await service.version()
