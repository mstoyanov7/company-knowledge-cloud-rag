from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from rag_api.services.auth import ClaimsToScopeMapper, OidcTokenValidator, TokenValidationError
from shared_schemas import AppSettings


def test_entra_token_validation_accepts_valid_token_and_extracts_claims() -> None:
    settings = AppSettings(
        app_env="test",
        auth_enabled=True,
        auth_tenant_id="tenant-123",
        auth_client_id="api-client-123",
        auth_group_scope_map_json='{"group-hr":["employees"]}',
        auth_role_scope_map_json='{"RAG.Engineering":["engineering"]}',
    )
    private_key, jwks = _test_keypair()
    token = _token(
        private_key,
        {
            "aud": "api-client-123",
            "iss": "https://login.microsoftonline.com/tenant-123/v2.0",
            "tid": "tenant-123",
            "oid": "user-123",
            "sub": "subject-123",
            "email": "user@example.com",
            "groups": ["group-hr"],
            "roles": ["RAG.Engineering"],
            "scp": "access_as_user",
        },
    )

    result = OidcTokenValidator(settings, jwks=jwks).validate(token)
    user_context = ClaimsToScopeMapper(settings).map_to_user_context(result)

    assert result.user_id == "user-123"
    assert result.tenant_id == "tenant-123"
    assert result.groups == ["group-hr"]
    assert user_context.acl_tags == ["employees", "engineering", "public"]


def test_entra_token_validation_rejects_wrong_audience() -> None:
    settings = AppSettings(
        app_env="test",
        auth_enabled=True,
        auth_tenant_id="tenant-123",
        auth_client_id="api-client-123",
    )
    private_key, jwks = _test_keypair()
    token = _token(
        private_key,
        {
            "aud": "other-client",
            "iss": "https://login.microsoftonline.com/tenant-123/v2.0",
            "tid": "tenant-123",
            "oid": "user-123",
            "sub": "subject-123",
        },
    )

    with pytest.raises(TokenValidationError):
        OidcTokenValidator(settings, jwks=jwks).validate(token)


def _test_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "test-key", "use": "sig", "alg": "RS256"})
    return private_key, {"keys": [public_jwk]}


def _token(private_key, claims: dict) -> str:
    now = datetime.now(UTC)
    payload = {
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
        **claims,
    }
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "test-key"})
