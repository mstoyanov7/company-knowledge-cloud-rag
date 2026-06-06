from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from shared_schemas.documents import UserContext

AccountStatus = Literal["pending", "active", "suspended", "rejected"]
AppRole = Literal["user", "system_admin"]


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=1024)
    name: str = Field(min_length=1, max_length=200)
    role: str | None = Field(default=None, max_length=120)
    dept: str | None = Field(default=None, max_length=120)


class UserProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, max_length=120)
    dept: str | None = Field(default=None, max_length=120)


class UserProfile(BaseModel):
    user_id: str
    email: str
    name: str
    tenant_id: str
    acl_tags: list[str] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    role: str | None = None
    dept: str | None = None
    status: AccountStatus = "active"
    app_role: AppRole = "user"
    approved_by_user_id: str | None = None
    approved_at_utc: datetime | None = None
    last_login_at_utc: datetime | None = None
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at_utc: datetime | None = None
    updated_by_user_id: str | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at_utc: datetime
    user: UserProfile


class RegistrationResponse(BaseModel):
    success: bool = True
    email: str
    status: AccountStatus = "pending"
    message: str = "Your request is pending administrator approval."


class LogoutResponse(BaseModel):
    success: bool = True


class AdminUserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: AccountStatus | None = None
    app_role: AppRole | None = None
    role: str | None = Field(default=None, max_length=120)
    dept: str | None = Field(default=None, max_length=120)
    acl_tags: list[str] | None = None


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
