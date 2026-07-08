from __future__ import annotations

from fastapi.testclient import TestClient

from rag_api.main import create_app
from shared_schemas import AppSettings


def test_access_request_requires_admin_approval_before_chat(tmp_path) -> None:
    client = _client(tmp_path)

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "alex@example.com",
            "password": "password-123",
            "name": "Alex Morgan",
            "dept": "Engineering",
        },
    )
    assert register_response.status_code == 200
    assert register_response.json()["status"] == "pending"
    assert "access_token" not in register_response.json()

    blocked_login = client.post(
        "/api/v1/auth/login",
        json={"email": "alex@example.com", "password": "password-123"},
    )
    assert blocked_login.status_code == 401
    assert "pending administrator approval" in blocked_login.json()["detail"]

    admin_token = _login(client, "admin@example.com", "admin-password-123")
    users_response = client.get("/api/v1/admin/users", headers=_auth(admin_token))
    pending_user = next(user for user in users_response.json() if user["email"] == "alex@example.com")

    approve_response = client.post(
        f"/api/v1/admin/users/{pending_user['user_id']}/approve",
        headers=_auth(admin_token),
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "active"

    user_token = _login(client, "alex@example.com", "password-123")
    answer_response = client.post(
        "/api/v1/answer",
        headers=_auth(user_token),
        json={"question": "What should I do on day one?"},
    )
    assert answer_response.status_code == 200
    assert set(answer_response.json()["retrieval_meta"]["access_scope"]["allowed_acl_tags"]) == {"public", "employees"}

    suspend_response = client.post(
        f"/api/v1/admin/users/{pending_user['user_id']}/suspend",
        headers=_auth(admin_token),
    )
    assert suspend_response.status_code == 200
    assert suspend_response.json()["status"] == "suspended"

    suspended_chat = client.post(
        "/api/v1/answer",
        headers=_auth(user_token),
        json={"question": "Can I still chat?"},
    )
    assert suspended_chat.status_code == 401


def test_admin_apis_require_system_admin(tmp_path) -> None:
    client = _client(tmp_path)
    admin_token = _login(client, "admin@example.com", "admin-password-123")

    client.post(
        "/api/v1/auth/register",
        json={
            "email": "user@example.com",
            "password": "password-123",
            "name": "Normal User",
        },
    )
    user_id = next(
        user["user_id"]
        for user in client.get("/api/v1/admin/users", headers=_auth(admin_token)).json()
        if user["email"] == "user@example.com"
    )
    client.post(f"/api/v1/admin/users/{user_id}/approve", headers=_auth(admin_token))
    user_token = _login(client, "user@example.com", "password-123")

    forbidden = client.get("/api/v1/admin/users", headers=_auth(user_token))
    assert forbidden.status_code == 403


def test_admin_topics_control_public_topic_visibility(tmp_path) -> None:
    client = _client(tmp_path)
    admin_token = _login(client, "admin@example.com", "admin-password-123")
    # ACL gating is verified against a regular employee (public, employees);
    # the admin bypasses ACL tags and is checked separately below.
    employee_token = _register_and_approve(client, admin_token, "employee@example.com", "employee-pass-123")

    create_response = client.post(
        "/api/v1/admin/topics",
        headers=_auth(admin_token),
        json={
            "id": "finance-admin-only",
            "name": "Finance Admin Only",
            "description": "Finance-only administrative topic.",
            "icon": "wallet",
            "acl_tags": ["finance"],
            "source_filters": ["onenote"],
            "retrieval_tags": ["finance"],
            "suggested_questions": ["What finance rules apply?"],
            "enabled": True,
        },
    )
    assert create_response.status_code == 200

    visible_for_employees = client.get("/api/v1/topics", headers=_auth(employee_token)).json()
    assert "finance-admin-only" not in {topic["id"] for topic in visible_for_employees}

    # Admins bypass ACL tags entirely, so a finance-only topic is still visible.
    visible_for_admin = client.get("/api/v1/topics", headers=_auth(admin_token)).json()
    assert "finance-admin-only" in {topic["id"] for topic in visible_for_admin}

    client.patch(
        "/api/v1/admin/topics/finance-admin-only",
        headers=_auth(admin_token),
        json={"acl_tags": ["employees"], "retrieval_tags": ["finance", "budget"]},
    )
    visible_after_acl_change = client.get("/api/v1/topics", headers=_auth(employee_token)).json()
    assert "finance-admin-only" in {topic["id"] for topic in visible_after_acl_change}

    client.delete("/api/v1/admin/topics/finance-admin-only", headers=_auth(admin_token))
    visible_after_disable = client.get("/api/v1/topics", headers=_auth(employee_token)).json()
    assert "finance-admin-only" not in {topic["id"] for topic in visible_after_disable}


def test_branding_settings_persist_through_public_api(tmp_path) -> None:
    client = _client(tmp_path)
    admin_token = _login(client, "admin@example.com", "admin-password-123")

    default_response = client.get("/api/v1/ui-settings")
    assert default_response.status_code == 200
    assert default_response.json()["app_name"] == "Company Knowledge"

    update_response = client.patch(
        "/api/v1/admin/ui-settings",
        headers=_auth(admin_token),
        json={
            "app_name": "Atlas Knowledge",
            "app_subtitle": "Company Assistant",
            "accent_hue": 155,
            "logo_text": "AK",
        },
    )
    assert update_response.status_code == 200

    public_response = client.get("/api/v1/ui-settings")
    assert public_response.json()["app_name"] == "Atlas Knowledge"
    assert public_response.json()["accent_hue"] == 155
    assert public_response.json()["logo_text"] == "AK"


def _client(tmp_path) -> TestClient:
    settings = AppSettings(
        app_env="test",
        app_database_url=f"sqlite:///{tmp_path / 'rag-api.sqlite3'}",
        rag_api_key="",
        mock_api_key="test-key",
        retrieval_provider="mock",
        default_llm_provider="mock",
        default_model_name="mock-onboarding-assistant",
        auth_required=True,
        auth_registration_tenant_id="local-tenant",
        auth_registration_acl_tags="public,employees",
        auth_default_acl_tags="public",
        auth_bootstrap_admin_email="admin@example.com",
        auth_bootstrap_admin_password="admin-password-123",
        auth_bootstrap_admin_name="System Administrator",
        security_audit_enabled=False,
    )
    return TestClient(create_app(settings))


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.json()
    return response.json()["access_token"]


def _register_and_approve(client: TestClient, admin_token: str, email: str, password: str) -> str:
    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": "Employee"},
    )
    assert register_response.status_code == 200, register_response.json()
    users = client.get("/api/v1/admin/users", headers=_auth(admin_token)).json()
    user_id = next(user["user_id"] for user in users if user["email"] == email)
    approve = client.post(f"/api/v1/admin/users/{user_id}/approve", headers=_auth(admin_token))
    assert approve.status_code == 200, approve.json()
    return _login(client, email, password)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
