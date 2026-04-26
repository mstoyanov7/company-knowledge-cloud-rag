from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from shared_schemas.documents import UserContext


class TokenValidationResult(BaseModel):
    subject: str
    tenant_id: str
    user_id: str
    email: str
    name: str | None = None
    groups: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    claims: dict[str, Any] = Field(default_factory=dict)


class AuthenticatedPrincipal(BaseModel):
    token: TokenValidationResult
    user_context: UserContext
    mapped_acl_tags: list[str] = Field(default_factory=list)


class SecurityAuditEvent(BaseModel):
    event_type: str
    outcome: str
    actor_user_id: str | None = None
    tenant_id: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
