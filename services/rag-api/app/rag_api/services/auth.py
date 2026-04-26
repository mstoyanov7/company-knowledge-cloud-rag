from __future__ import annotations

import json
import logging
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.algorithms import RSAAlgorithm
from shared_schemas import AppSettings, AuthenticatedPrincipal, TokenValidationResult, UserContext

from rag_api.services.security_audit import SecurityAuditLogger


class TokenValidationError(ValueError):
    pass


class OidcTokenValidator:
    def __init__(
        self,
        settings: AppSettings,
        *,
        jwks: dict[str, Any] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings = settings
        self.jwks = jwks
        self.logger = logger or logging.getLogger("rag_api.auth")
        self._jwks_client: PyJWKClient | None = None

    def validate(self, token: str) -> TokenValidationResult:
        if not self.settings.auth_enabled:
            raise TokenValidationError("OIDC authentication is disabled.")
        if not self.settings.auth_audience_list:
            raise TokenValidationError("No allowed token audience is configured.")
        if not self.settings.auth_issuer:
            raise TokenValidationError("No token issuer is configured.")

        try:
            signing_key = self._signing_key_for_token(token)
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=self.settings.auth_audience_list,
                issuer=self.settings.auth_issuer,
                leeway=self.settings.auth_leeway_seconds,
                options={"require": ["exp", "iat", "iss", "aud"]},
            )
        except Exception as error:
            raise TokenValidationError(str(error)) from error

        tenant_id = str(claims.get("tid") or "")
        if self.settings.resolved_auth_tenant_id and tenant_id != self.settings.resolved_auth_tenant_id:
            raise TokenValidationError("Token tenant does not match configured tenant.")

        user_id = str(claims.get("oid") or claims.get("sub") or "")
        if not user_id:
            raise TokenValidationError("Token does not contain oid or sub.")

        scopes = _claim_list(claims.get("scp"), split_spaces=True)
        roles = _claim_list(claims.get(self.settings.auth_role_claim))
        required_scopes = set(self.settings.auth_required_scope_list)
        if required_scopes and not required_scopes.issubset(set(scopes).union(roles)):
            raise TokenValidationError("Token is missing required scopes or roles.")

        groups = _claim_list(claims.get(self.settings.auth_group_claim))
        if not groups and (claims.get("hasgroups") or (claims.get("_claim_names") or {}).get("groups")):
            self.logger.warning("event=auth_group_overage user_id=%s tenant_id=%s", user_id, tenant_id)

        return TokenValidationResult(
            subject=str(claims.get("sub") or user_id),
            tenant_id=tenant_id,
            user_id=user_id,
            email=str(claims.get("email") or claims.get("preferred_username") or claims.get("upn") or ""),
            name=claims.get("name"),
            groups=groups,
            roles=roles,
            scopes=scopes,
            claims=claims,
        )

    def _signing_key_for_token(self, token: str):
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if self.jwks is not None:
            for key in self.jwks.get("keys", []):
                if key.get("kid") == kid:
                    return RSAAlgorithm.from_jwk(json.dumps(key))
            raise TokenValidationError("No matching signing key found in configured JWKS.")

        if not self.settings.auth_metadata_url:
            raise TokenValidationError("No OIDC metadata URL is configured.")
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(
                self.settings.auth_metadata_url.replace(
                    "/.well-known/openid-configuration",
                    "/discovery/v2.0/keys",
                ),
                cache_keys=True,
                lifespan=self.settings.auth_jwks_cache_seconds,
            )
        return self._jwks_client.get_signing_key_from_jwt(token).key


class ClaimsToScopeMapper:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def map_to_user_context(self, token: TokenValidationResult) -> UserContext:
        acl_tags = set(self.settings.auth_default_acl_tag_list)
        for group in token.groups:
            acl_tags.update(self.settings.auth_group_scope_map.get(group, []))
        for role in token.roles:
            acl_tags.update(self.settings.auth_role_scope_map.get(role, []))

        return UserContext(
            user_id=token.user_id,
            email=token.email or f"{token.user_id}@unknown.local",
            tenant_id=token.tenant_id,
            acl_tags=sorted(tag for tag in acl_tags if tag),
            groups=sorted(token.groups),
            roles=sorted(token.roles),
        )


class AuthenticationService:
    def __init__(
        self,
        *,
        settings: AppSettings,
        validator: OidcTokenValidator,
        mapper: ClaimsToScopeMapper,
        audit: SecurityAuditLogger,
    ) -> None:
        self.settings = settings
        self.validator = validator
        self.mapper = mapper
        self.audit = audit

    def authenticate_bearer_token(self, token: str) -> AuthenticatedPrincipal:
        try:
            validation = self.validator.validate(token)
            user_context = self.mapper.map_to_user_context(validation)
            self.audit.record(
                "authentication",
                "success",
                actor_user_id=user_context.user_id,
                tenant_id=user_context.tenant_id,
                metadata={
                    "groups_count": len(user_context.groups),
                    "roles": user_context.roles,
                    "mapped_acl_tags": user_context.acl_tags,
                },
            )
            return AuthenticatedPrincipal(
                token=validation,
                user_context=user_context,
                mapped_acl_tags=user_context.acl_tags,
            )
        except TokenValidationError as error:
            self.audit.record(
                "authentication",
                "failure",
                metadata={"reason": str(error)},
            )
            raise


def _claim_list(value: Any, *, split_spaces: bool = False) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.split() if split_spaces else value.split(",")
        return [part.strip() for part in parts if part.strip()]
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    return [str(value).strip()] if str(value).strip() else []
