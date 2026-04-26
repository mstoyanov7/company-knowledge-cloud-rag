from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OpsJobStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    dead_letter = "dead_letter"


class OpsJobType(StrEnum):
    sharepoint_delta_catchup = "sharepoint_delta_catchup"
    sharepoint_reconciliation = "sharepoint_reconciliation"
    onenote_reconciliation = "onenote_reconciliation"
    graph_subscription_renewal = "graph_subscription_renewal"
    graph_subscription_reauthorize = "graph_subscription_reauthorize"
    sharepoint_subscription_ensure = "sharepoint_subscription_ensure"


class GraphSubscriptionStatus(StrEnum):
    active = "active"
    reauthorization_required = "reauthorization_required"
    removed = "removed"
    failed = "failed"


class GraphLifecycleEvent(StrEnum):
    reauthorization_required = "reauthorizationRequired"
    subscription_removed = "subscriptionRemoved"
    missed = "missed"


class OpsJobRecord(BaseModel):
    job_id: str
    job_type: str
    dedupe_key: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: OpsJobStatus = OpsJobStatus.pending
    attempts: int = 0
    max_attempts: int = 5
    available_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    locked_at_utc: datetime | None = None
    locked_by: str | None = None
    last_error: str | None = None
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at_utc: datetime | None = None


class DeadLetterRecord(BaseModel):
    dead_letter_id: str
    job_id: str
    job_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str
    attempts: int
    failed_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GraphSubscriptionRecord(BaseModel):
    subscription_id: str
    resource: str
    change_type: str
    notification_url: str
    lifecycle_notification_url: str | None = None
    client_state: str
    expiration_datetime_utc: datetime
    status: GraphSubscriptionStatus = GraphSubscriptionStatus.active
    reauthorization_required: bool = False
    last_renewal_attempt_utc: datetime | None = None
    last_successful_renewal_utc: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GraphResourceData(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str | None = None
    odata_type: str | None = Field(default=None, alias="@odata.type")
    odata_id: str | None = Field(default=None, alias="@odata.id")
    etag: str | None = Field(default=None, alias="@odata.etag")


class GraphChangeNotification(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    subscription_id: str = Field(alias="subscriptionId")
    subscription_expiration_datetime_utc: datetime | None = Field(
        default=None,
        alias="subscriptionExpirationDateTime",
    )
    tenant_id: str | None = Field(default=None, alias="tenantId")
    client_state: str | None = Field(default=None, alias="clientState")
    change_type: str | None = Field(default=None, alias="changeType")
    resource: str | None = None
    resource_data: GraphResourceData | None = Field(default=None, alias="resourceData")
    lifecycle_event: GraphLifecycleEvent | None = Field(default=None, alias="lifecycleEvent")


class GraphNotificationEnvelope(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    value: list[GraphChangeNotification] = Field(default_factory=list)


class GraphWebhookAccepted(BaseModel):
    accepted: bool = True
    notification_count: int = 0
    enqueued_count: int = 0
    duplicate_count: int = 0
    lifecycle_count: int = 0
