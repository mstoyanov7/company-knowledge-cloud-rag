from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from shared_schemas import (
    AdminSystemSettings,
    AdminSystemSettingsUpdate,
    AdminUserUpdate,
    AppSettings,
    ForceSyncResponse,
    OpsJobType,
    SystemRuntimeSettings,
    TopicAdmin,
    TopicCreateRequest,
    TopicUpdateRequest,
    UiSettings,
    UiSettingsUpdate,
    UserProfile,
)

from rag_api.dependencies import (
    RequestAuthContext,
    get_app_data_store,
    get_document_metadata,
    get_llm,
    get_local_auth_service,
    get_request_auth_context,
    get_runtime_settings,
)
from rag_api.persistence.app_store import AppDataStore, AppTopicRecord, UiSettingsRecord, json_dumps
from rag_api.services.local_auth import LocalAuthError, LocalAuthService
from rag_api.services.topic_sync import reconcile_topics_from_sources
from sync_worker.persistence import PostgresOpsStore

router = APIRouter(prefix="/api/v1", tags=["admin"])


def _require_system_admin(
    auth_context: RequestAuthContext = Depends(get_request_auth_context),
    service: LocalAuthService = Depends(get_local_auth_service),
) -> UserProfile:
    if auth_context.user_context is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No authenticated user session.")
    profile = service.profile_for_user_id(auth_context.user_context.user_id)
    if profile is None or profile.status != "active" or profile.app_role != "system_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System administrator access is required.")
    return profile


@router.get("/ui-settings", response_model=UiSettings)
async def public_ui_settings(store: AppDataStore = Depends(get_app_data_store)) -> UiSettings:
    return _ui_settings_from_record(store.get_ui_settings())


@router.get("/admin/users", response_model=list[UserProfile])
async def list_users(
    _admin: UserProfile = Depends(_require_system_admin),
    service: LocalAuthService = Depends(get_local_auth_service),
) -> list[UserProfile]:
    return service.list_users()


@router.patch("/admin/users/{user_id}", response_model=UserProfile)
async def update_user(
    user_id: str,
    request: AdminUserUpdate,
    admin: UserProfile = Depends(_require_system_admin),
    service: LocalAuthService = Depends(get_local_auth_service),
) -> UserProfile:
    _reject_self_lockout(admin, user_id, request)
    try:
        return service.update_user_admin(user_id, request, updated_by_user_id=admin.user_id)
    except LocalAuthError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post("/admin/users/{user_id}/approve", response_model=UserProfile)
async def approve_user(
    user_id: str,
    admin: UserProfile = Depends(_require_system_admin),
    service: LocalAuthService = Depends(get_local_auth_service),
) -> UserProfile:
    try:
        return service.approve_user(user_id, approved_by_user_id=admin.user_id)
    except LocalAuthError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post("/admin/users/{user_id}/reject", response_model=UserProfile)
async def reject_user(
    user_id: str,
    admin: UserProfile = Depends(_require_system_admin),
    service: LocalAuthService = Depends(get_local_auth_service),
) -> UserProfile:
    _reject_self_lockout(admin, user_id, AdminUserUpdate(status="rejected"))
    try:
        return service.reject_user(user_id, updated_by_user_id=admin.user_id)
    except LocalAuthError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post("/admin/users/{user_id}/suspend", response_model=UserProfile)
async def suspend_user(
    user_id: str,
    admin: UserProfile = Depends(_require_system_admin),
    service: LocalAuthService = Depends(get_local_auth_service),
) -> UserProfile:
    _reject_self_lockout(admin, user_id, AdminUserUpdate(status="suspended"))
    try:
        return service.suspend_user(user_id, updated_by_user_id=admin.user_id)
    except LocalAuthError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/admin/topics", response_model=list[TopicAdmin])
async def list_admin_topics(
    _admin: UserProfile = Depends(_require_system_admin),
    store: AppDataStore = Depends(get_app_data_store),
) -> list[TopicAdmin]:
    return [_topic_admin_from_record(record) for record in store.list_topic_records(enabled_only=False)]


@router.post("/admin/topics", response_model=TopicAdmin)
async def create_topic(
    request: TopicCreateRequest,
    admin: UserProfile = Depends(_require_system_admin),
    store: AppDataStore = Depends(get_app_data_store),
) -> TopicAdmin:
    existing = store.get_topic_record(request.id, enabled_only=False)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A topic with that id already exists.")
    record = store.upsert_topic_record(
        request.id,
        _topic_updates(request.model_dump()),
        updated_by_user_id=admin.user_id,
    )
    return _topic_admin_from_record(record)


@router.post("/admin/topics/refresh-from-sources", response_model=list[TopicAdmin])
async def refresh_topics_from_sources(
    _admin: UserProfile = Depends(_require_system_admin),
    store: AppDataStore = Depends(get_app_data_store),
    settings: AppSettings = Depends(get_runtime_settings),
) -> list[TopicAdmin]:
    records = reconcile_topics_from_sources(
        get_document_metadata(settings),
        store,
        settings,
        prune_stale=settings.retrieval_provider == "qdrant",
    )
    return [_topic_admin_from_record(record) for record in records]


@router.patch("/admin/topics/{topic_id}", response_model=TopicAdmin)
async def update_topic(
    topic_id: str,
    request: TopicUpdateRequest,
    admin: UserProfile = Depends(_require_system_admin),
    store: AppDataStore = Depends(get_app_data_store),
) -> TopicAdmin:
    if store.get_topic_record(topic_id, enabled_only=False) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found.")
    record = store.upsert_topic_record(
        topic_id,
        _topic_updates(request.model_dump(exclude_unset=True)),
        updated_by_user_id=admin.user_id,
    )
    return _topic_admin_from_record(record)


@router.delete("/admin/topics/{topic_id}", response_model=TopicAdmin)
async def disable_topic(
    topic_id: str,
    admin: UserProfile = Depends(_require_system_admin),
    store: AppDataStore = Depends(get_app_data_store),
) -> TopicAdmin:
    if store.get_topic_record(topic_id, enabled_only=False) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found.")
    record = store.upsert_topic_record(topic_id, {"enabled": False}, updated_by_user_id=admin.user_id)
    return _topic_admin_from_record(record)


@router.get("/admin/ui-settings", response_model=UiSettings)
async def admin_ui_settings(
    _admin: UserProfile = Depends(_require_system_admin),
    store: AppDataStore = Depends(get_app_data_store),
) -> UiSettings:
    return _ui_settings_from_record(store.get_ui_settings())


@router.patch("/admin/ui-settings", response_model=UiSettings)
async def update_ui_settings(
    request: UiSettingsUpdate,
    admin: UserProfile = Depends(_require_system_admin),
    store: AppDataStore = Depends(get_app_data_store),
) -> UiSettings:
    record = store.update_ui_settings(request.model_dump(exclude_unset=True), updated_by_user_id=admin.user_id)
    return _ui_settings_from_record(record)


@router.get("/admin/system-settings", response_model=AdminSystemSettings)
async def admin_system_settings(
    _admin: UserProfile = Depends(_require_system_admin),
    settings: AppSettings = Depends(get_runtime_settings),
) -> AdminSystemSettings:
    return await _admin_system_settings(settings)


@router.patch("/admin/system-settings", response_model=AdminSystemSettings)
async def update_system_settings(
    request: AdminSystemSettingsUpdate,
    admin: UserProfile = Depends(_require_system_admin),
    settings: AppSettings = Depends(get_runtime_settings),
) -> AdminSystemSettings:
    updates = request.model_dump(exclude_unset=True)
    store = PostgresOpsStore(settings)
    current = store.get_system_runtime_settings()
    model_name = updates.get("llm_model")
    if model_name is not None:
        cleaned_model = str(model_name).strip()
        if not cleaned_model:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Model name is required.")
        available_models = await _available_llm_models(settings, selected_model=current.llm_model)
        if cleaned_model not in available_models:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select one of the available LLM models.")
        updates["llm_model"] = cleaned_model

    runtime = store.update_system_runtime_settings(
        updates,
        updated_by_user_id=admin.user_id,
    )
    return await _admin_system_settings(settings, runtime=runtime)


@router.post("/admin/system-sync/run", response_model=ForceSyncResponse)
async def force_system_sync(
    admin: UserProfile = Depends(_require_system_admin),
    settings: AppSettings = Depends(get_runtime_settings),
) -> ForceSyncResponse:
    store = PostgresOpsStore(settings)
    now = datetime.now(UTC)
    job, created = store.enqueue_job(
        OpsJobType.onenote_reconciliation.value,
        {
            "trigger": "admin",
            "actor_user_id": admin.user_id,
            "requested_at_utc": now.isoformat(),
        },
        dedupe_key=f"admin:{OpsJobType.onenote_reconciliation.value}:{now.timestamp()}:{uuid4().hex[:8]}",
        max_attempts=settings.ops_job_max_attempts,
        available_at_utc=now,
    )
    return ForceSyncResponse(job=job, created=created, settings=await _admin_system_settings(settings))


def _reject_self_lockout(admin: UserProfile, user_id: str, request: AdminUserUpdate) -> None:
    if admin.user_id != user_id:
        return
    if request.status is not None and request.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot deactivate your own admin account.")
    if request.app_role is not None and request.app_role != "system_admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot remove your own admin role.")


def _topic_updates(values: dict) -> dict:
    updates = dict(values)
    for request_key, store_key in {
        "acl_tags": "acl_tags_json",
        "source_filters": "source_filters_json",
        "section_filters": "section_filters_json",
        "retrieval_tags": "retrieval_tags_json",
        "suggested_questions": "suggested_questions_json",
    }.items():
        if request_key in updates:
            updates[store_key] = json_dumps(_normalize_list(updates.pop(request_key)))
    return updates


def _topic_admin_from_record(record: AppTopicRecord) -> TopicAdmin:
    return TopicAdmin(
        id=record.topic_id,
        name=record.name,
        description=record.description,
        icon=record.icon,
        acl_tags=_json_list(record.acl_tags_json),
        source_filters=_json_list(record.source_filters_json),
        section_filters=_json_list(record.section_filters_json),
        retrieval_tags=_json_list(record.retrieval_tags_json),
        suggested_questions=_json_list(record.suggested_questions_json),
        section_key=record.section_key,
        auto_managed=record.auto_managed,
        enabled=record.enabled,
        created_at_utc=record.created_at_utc,
        updated_at_utc=record.updated_at_utc,
        updated_by_user_id=record.updated_by_user_id,
    )


def _ui_settings_from_record(record: UiSettingsRecord) -> UiSettings:
    return UiSettings(
        app_name=record.app_name,
        app_subtitle=record.app_subtitle,
        accent_hue=record.accent_hue,
        logo_url=record.logo_url,
        logo_text=record.logo_text,
        updated_at_utc=record.updated_at_utc,
        updated_by_user_id=record.updated_by_user_id,
    )


async def _admin_system_settings(
    settings: AppSettings,
    *,
    runtime: SystemRuntimeSettings | None = None,
) -> AdminSystemSettings:
    store = PostgresOpsStore(settings)
    runtime = runtime or store.get_system_runtime_settings()
    available_models = await _available_llm_models(settings, selected_model=runtime.llm_model)
    if runtime.llm_model not in available_models:
        available_models = [runtime.llm_model, *available_models]
    return AdminSystemSettings(
        llm_provider=settings.default_llm_provider,
        llm_model=runtime.llm_model,
        available_llm_models=available_models,
        onenote_sync_interval_seconds=runtime.onenote_sync_interval_seconds,
        onenote_sync_daily_time=runtime.onenote_sync_daily_time,
        onenote_sync_timezone=settings.onenote_sync_timezone,
        onenote_sync_paused=runtime.onenote_sync_paused,
        updated_at_utc=runtime.updated_at_utc,
        updated_by_user_id=runtime.updated_by_user_id,
        last_sync_job=store.latest_job(OpsJobType.onenote_reconciliation.value),
    )


async def _available_llm_models(settings: AppSettings, *, selected_model: str) -> list[str]:
    try:
        models = await asyncio.wait_for(get_llm(settings, model_name=selected_model).list_models(), timeout=5)
    except Exception:
        models = [selected_model]
    unique = sorted({model.strip() for model in models if model.strip()})
    return unique or [selected_model]


def _normalize_list(values: list[str]) -> list[str]:
    return [value.strip() for value in values if value.strip()]


def _json_list(value: str | None) -> list[str]:
    import json

    if not value:
        return []
    parsed = json.loads(value)
    return [str(item) for item in parsed] if isinstance(parsed, list) else []
