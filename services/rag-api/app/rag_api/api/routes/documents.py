from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from shared_schemas import AppSettings, DocumentDetail, DocumentSummary, Notebook, TrendingQuestion, UserContext

from rag_api.dependencies import (
    RequestAuthContext,
    effective_user_context,
    get_document_service,
    get_query_log_service,
    get_request_auth_context,
    get_runtime_settings,
)
from rag_api.services import DocumentService, QueryLogService

router = APIRouter(prefix="/api/v1", tags=["documents"])


@router.get("/notebooks", response_model=list[Notebook])
async def notebooks(
    x_user_id: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_acl_tags: str | None = Header(default=None),
    auth_context: RequestAuthContext = Depends(get_request_auth_context),
    settings: AppSettings = Depends(get_runtime_settings),
    service: DocumentService = Depends(get_document_service),
) -> list[Notebook]:
    user_context = _user_context(auth_context, settings, x_user_id, x_user_email, x_tenant_id, x_acl_tags)
    return service.list_notebooks(user_context)


@router.get("/documents", response_model=list[DocumentSummary])
async def documents(
    sort: str = Query(default="recently_updated", pattern="^(recently_updated|title)$"),
    limit: int = Query(default=10, ge=1, le=100),
    x_user_id: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_acl_tags: str | None = Header(default=None),
    auth_context: RequestAuthContext = Depends(get_request_auth_context),
    settings: AppSettings = Depends(get_runtime_settings),
    service: DocumentService = Depends(get_document_service),
) -> list[DocumentSummary]:
    user_context = _user_context(auth_context, settings, x_user_id, x_user_email, x_tenant_id, x_acl_tags)
    return service.list_documents(user_context, sort=sort, limit=limit)


@router.get("/documents/detail", response_model=DocumentDetail)
async def document_detail(
    source_item_id: str = Query(min_length=1),
    source_system: str | None = Query(default=None, min_length=1),
    x_user_id: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_acl_tags: str | None = Header(default=None),
    auth_context: RequestAuthContext = Depends(get_request_auth_context),
    settings: AppSettings = Depends(get_runtime_settings),
    service: DocumentService = Depends(get_document_service),
) -> DocumentDetail:
    user_context = _user_context(auth_context, settings, x_user_id, x_user_email, x_tenant_id, x_acl_tags)
    detail = service.get_document_detail(user_context, source_item_id=source_item_id, source_system=source_system)
    if detail is None:
        raise HTTPException(status_code=404, detail="Source document not found or not accessible.")
    return detail


@router.get("/attachments/{download_id}/download")
async def attachment_download(
    download_id: str,
    x_user_id: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_acl_tags: str | None = Header(default=None),
    auth_context: RequestAuthContext = Depends(get_request_auth_context),
    settings: AppSettings = Depends(get_runtime_settings),
    service: DocumentService = Depends(get_document_service),
):
    user_context = _user_context(auth_context, settings, x_user_id, x_user_email, x_tenant_id, x_acl_tags)
    attachment = service.get_attachment_for_download(user_context, download_id=download_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found or not accessible.")
    if not attachment.storage_path:
        return RedirectResponse(attachment.resource_url)

    storage_root = Path(settings.attachment_storage_dir).resolve()
    target = (storage_root / attachment.storage_path).resolve()
    if not _is_relative_to(target, storage_root) or not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Attachment file is not available.")
    return FileResponse(
        path=target,
        media_type=attachment.mime_type or "application/octet-stream",
        filename=attachment.file_name,
    )


@router.get("/trending", response_model=list[TrendingQuestion])
async def trending(
    window: str = Query(default="30d", min_length=2, max_length=10),
    limit: int = Query(default=10, ge=1, le=50),
    x_user_id: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_acl_tags: str | None = Header(default=None),
    auth_context: RequestAuthContext = Depends(get_request_auth_context),
    settings: AppSettings = Depends(get_runtime_settings),
    service: QueryLogService = Depends(get_query_log_service),
) -> list[TrendingQuestion]:
    user_context = _user_context(auth_context, settings, x_user_id, x_user_email, x_tenant_id, x_acl_tags)
    return service.trending(user_context=user_context, window=window, limit=limit)


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


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False

