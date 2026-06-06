from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from shared_schemas import (
    AdminUserUpdate,
    AppSettings,
    AuthResponse,
    LoginRequest,
    RegistrationResponse,
    RegisterRequest,
    UserContext,
    UserProfile,
    UserProfileUpdate,
)

from rag_api.persistence.app_store import AppDataStore, AppStoreConflict, SessionRecord, UserRecord, json_dumps
from rag_api.services.auth import TokenValidationError

try:
    import bcrypt
except ModuleNotFoundError:  # pragma: no cover - dependency fallback for minimal local envs
    bcrypt = None


class LocalAuthError(ValueError):
    pass


class LocalAuthService:
    def __init__(self, *, settings: AppSettings, store: AppDataStore) -> None:
        self.settings = settings
        self.store = store

    def register(self, request: RegisterRequest) -> RegistrationResponse:
        now = _utcnow()
        user = UserRecord(
            user_id=f"usr-{uuid4().hex}",
            email=_normalize_email(request.email),
            password_hash=_hash_password(request.password),
            name=request.name.strip(),
            tenant_id=self.settings.auth_registration_tenant_id
            or self.settings.resolved_auth_tenant_id
            or "local-tenant",
            acl_tags_json=json_dumps(self.settings.auth_registration_acl_tag_list),
            groups_json=json_dumps([]),
            roles_json=json_dumps([request.role] if request.role else []),
            role=request.role,
            dept=request.dept,
            status="pending",
            app_role="user",
            approved_by_user_id=None,
            approved_at_utc=None,
            last_login_at_utc=None,
            created_at_utc=now,
            updated_at_utc=now,
            updated_by_user_id=None,
        )
        try:
            created = self.store.create_user(user)
        except AppStoreConflict as error:
            raise LocalAuthError(str(error)) from error
        return RegistrationResponse(email=created.email)

    def login(self, request: LoginRequest) -> AuthResponse:
        user = self.store.get_user_by_email(request.email)
        if user is None or not _verify_password(request.password, user.password_hash):
            raise LocalAuthError("Invalid email or password.")
        if user.status != "active":
            raise LocalAuthError(_blocked_login_message(user.status))
        return self._issue_session(user)

    def authenticate_bearer_token(self, token: str) -> tuple[UserContext, UserProfile]:
        try:
            payload = jwt.decode(
                token,
                self.settings.auth_session_secret.get_secret_value(),
                algorithms=["HS256"],
                options={"require": ["exp", "iat", "sid", "sub"]},
            )
        except Exception as error:
            raise TokenValidationError("Invalid or expired session token.") from error

        session_id = str(payload.get("sid") or "")
        if not session_id:
            raise TokenValidationError("Invalid session token.")
        active = self.store.get_active_session(session_id)
        if active is None:
            raise TokenValidationError("Session is expired or has been revoked.")
        session, user = active
        if user.status != "active":
            self.store.revoke_session(session.session_id)
            raise TokenValidationError(_blocked_login_message(user.status))
        profile = profile_from_record(user)
        return user_context_from_profile(profile), profile

    def profile_for_user_id(self, user_id: str) -> UserProfile | None:
        record = self.store.get_user_by_id(user_id)
        return profile_from_record(record) if record is not None else None

    def logout(self, token: str) -> None:
        try:
            payload = jwt.decode(
                token,
                self.settings.auth_session_secret.get_secret_value(),
                algorithms=["HS256"],
                options={"verify_exp": False, "require": ["sid"]},
            )
        except Exception as error:
            raise TokenValidationError("Invalid session token.") from error
        self.store.revoke_session(str(payload.get("sid") or ""))

    def update_profile(self, user_id: str, request: UserProfileUpdate) -> UserProfile:
        record = self.store.update_user_profile(
            user_id,
            name=request.name.strip() if request.name is not None else None,
            role=request.role if request.role is not None else None,
            dept=request.dept if request.dept is not None else None,
        )
        if record is None:
            raise LocalAuthError("User not found.")
        return profile_from_record(record)

    def bootstrap_admin(self) -> UserProfile | None:
        email = _normalize_email(self.settings.auth_bootstrap_admin_email)
        password = self.settings.auth_bootstrap_admin_password.get_secret_value()
        if not email or not password:
            return None

        now = _utcnow()
        existing = self.store.get_user_by_email(email)
        configured_name = self.settings.auth_bootstrap_admin_name.strip()
        name = configured_name or (existing.name if existing is not None else email)
        updates = {
            "name": name,
            "password_hash": _hash_password(password),
            "status": "active",
            "app_role": "system_admin",
            "acl_tags_json": json_dumps(self.settings.auth_registration_acl_tag_list),
            "approved_at_utc": now,
            "approved_by_user_id": "bootstrap",
        }
        if existing is not None:
            promoted = self.store.update_user_admin(existing.user_id, updates, updated_by_user_id="bootstrap")
            return profile_from_record(promoted) if promoted is not None else None

        user = UserRecord(
            user_id=f"usr-{uuid4().hex}",
            email=email,
            password_hash=updates["password_hash"],
            name=name,
            tenant_id=self.settings.auth_registration_tenant_id
            or self.settings.resolved_auth_tenant_id
            or "local-tenant",
            acl_tags_json=updates["acl_tags_json"],
            groups_json=json_dumps([]),
            roles_json=json_dumps(["system_admin"]),
            role="System Administrator",
            dept=None,
            status="active",
            app_role="system_admin",
            approved_by_user_id="bootstrap",
            approved_at_utc=now,
            last_login_at_utc=None,
            created_at_utc=now,
            updated_at_utc=now,
            updated_by_user_id="bootstrap",
        )
        try:
            created = self.store.create_user(user)
        except AppStoreConflict as error:
            raise LocalAuthError(str(error)) from error
        return profile_from_record(created)

    def list_users(self) -> list[UserProfile]:
        status_rank = {"pending": 0, "active": 1, "suspended": 2, "rejected": 3}
        users = [profile_from_record(record) for record in self.store.list_users()]
        return sorted(users, key=lambda user: (status_rank.get(user.status, 99), user.email))

    def update_user_admin(
        self,
        user_id: str,
        request: AdminUserUpdate,
        *,
        updated_by_user_id: str,
    ) -> UserProfile:
        updates: dict[str, object] = {}
        fields = request.model_fields_set
        if "name" in fields:
            updates["name"] = request.name.strip() if request.name is not None else request.name
        if "status" in fields and request.status is not None:
            updates["status"] = request.status
            if request.status == "active":
                updates["approved_at_utc"] = _utcnow()
                updates["approved_by_user_id"] = updated_by_user_id
            elif request.status in {"pending", "rejected", "suspended"}:
                updates["approved_at_utc"] = None
                updates["approved_by_user_id"] = None
        if "app_role" in fields and request.app_role is not None:
            updates["app_role"] = request.app_role
        if "role" in fields:
            updates["role"] = request.role
        if "dept" in fields:
            updates["dept"] = request.dept
        if "acl_tags" in fields and request.acl_tags is not None:
            updates["acl_tags_json"] = json_dumps(_normalize_list(request.acl_tags))
        record = self.store.update_user_admin(user_id, updates, updated_by_user_id=updated_by_user_id)
        if record is None:
            raise LocalAuthError("User not found.")
        return profile_from_record(record)

    def approve_user(self, user_id: str, *, approved_by_user_id: str) -> UserProfile:
        return self.update_user_admin(
            user_id,
            AdminUserUpdate(status="active"),
            updated_by_user_id=approved_by_user_id,
        )

    def reject_user(self, user_id: str, *, updated_by_user_id: str) -> UserProfile:
        return self.update_user_admin(
            user_id,
            AdminUserUpdate(status="rejected"),
            updated_by_user_id=updated_by_user_id,
        )

    def suspend_user(self, user_id: str, *, updated_by_user_id: str) -> UserProfile:
        return self.update_user_admin(
            user_id,
            AdminUserUpdate(status="suspended"),
            updated_by_user_id=updated_by_user_id,
        )

    def _issue_session(self, user: UserRecord) -> AuthResponse:
        now = _utcnow()
        expires = now + timedelta(hours=max(1, self.settings.auth_session_ttl_hours))
        session_id = f"ses-{uuid4().hex}"
        self.store.create_session(
            SessionRecord(
                session_id=session_id,
                user_id=user.user_id,
                expires_at_utc=expires,
                created_at_utc=now,
                revoked_at_utc=None,
            )
        )
        user = self.store.record_last_login(user.user_id, now) or user
        token = jwt.encode(
            {
                "sub": user.user_id,
                "sid": session_id,
                "email": user.email,
                "tenant_id": user.tenant_id,
                "iat": int(now.timestamp()),
                "exp": int(expires.timestamp()),
            },
            self.settings.auth_session_secret.get_secret_value(),
            algorithm="HS256",
        )
        return AuthResponse(access_token=token, expires_at_utc=expires, user=profile_from_record(user))


def profile_from_record(record: UserRecord) -> UserProfile:
    return UserProfile(
        user_id=record.user_id,
        email=record.email,
        name=record.name,
        tenant_id=record.tenant_id,
        acl_tags=_json_list(record.acl_tags_json),
        groups=_json_list(record.groups_json),
        roles=_json_list(record.roles_json),
        role=record.role,
        dept=record.dept,
        status=record.status,
        app_role=record.app_role,
        approved_by_user_id=record.approved_by_user_id,
        approved_at_utc=record.approved_at_utc,
        last_login_at_utc=record.last_login_at_utc,
        created_at_utc=record.created_at_utc,
        updated_at_utc=record.updated_at_utc,
        updated_by_user_id=record.updated_by_user_id,
    )


def user_context_from_profile(profile: UserProfile) -> UserContext:
    return UserContext(
        user_id=profile.user_id,
        email=profile.email,
        tenant_id=profile.tenant_id,
        acl_tags=profile.acl_tags,
        groups=profile.groups,
        roles=profile.roles,
    )


def _hash_password(password: str) -> str:
    if bcrypt is not None:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 390000)
    return "pbkdf2_sha256$390000$%s$%s" % (
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def _verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("$2") and bcrypt is not None:
        return bool(bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8")))
    if password_hash.startswith("pbkdf2_sha256$"):
        try:
            _scheme, iterations, raw_salt, raw_digest = password_hash.split("$", maxsplit=3)
            salt = base64.b64decode(raw_salt)
            expected = base64.b64decode(raw_digest)
            actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        except Exception:
            return False
        return hmac.compare_digest(actual, expected)
    return False


def _json_list(value: str) -> list[str]:
    import json

    parsed = json.loads(value or "[]")
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _normalize_list(values: list[str]) -> list[str]:
    return [value.strip() for value in values if value.strip()]


def _blocked_login_message(status: str) -> str:
    if status == "pending":
        return "Your account request is pending administrator approval."
    if status == "rejected":
        return "Your account request was rejected. Contact your system administrator."
    if status == "suspended":
        return "Your account is suspended. Contact your system administrator."
    return "Your account is not active. Contact your system administrator."


def _utcnow() -> datetime:
    return datetime.now(UTC)
