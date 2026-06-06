from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from rag_api.dependencies import get_document_service
from rag_api.main import create_app
from rag_api.services import AccessScopeResolver, DocumentService
from shared_schemas import AppSettings, SourceAttachment, SourceDocument, UserContext


def create_feature_client(tmp_path: Path) -> TestClient:
    settings = AppSettings(
        app_env="test",
        mock_api_key="test-key",
        rag_api_key="test-rag-key",
        retrieval_provider="mock",
        default_llm_provider="mock",
        default_model_name="mock-onboarding-assistant",
        security_audit_enabled=False,
        auth_registration_acl_tags="public",
        auth_bootstrap_admin_email="admin@example.com",
        auth_bootstrap_admin_password="admin-password-123",
        auth_bootstrap_admin_name="System Administrator",
        app_database_url=f"sqlite:///{tmp_path / 'app.sqlite'}",
    )
    return TestClient(create_app(settings))


def _source_document(
    title: str,
    *,
    source_item_id: str,
    last_modified_utc: datetime,
    updated_at_utc: datetime | None,
) -> SourceDocument:
    return SourceDocument(
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="onenote/Cloud-RAG",
        source_item_id=source_item_id,
        source_url=f"https://example.test/{source_item_id}",
        title=title,
        file_name=f"{title}.one",
        file_extension="one",
        mime_type="text/html",
        section_path="Cloud-RAG / Tests",
        last_modified_utc=last_modified_utc,
        updated_at_utc=updated_at_utc,
        acl_tags=["employees"],
        content_hash=f"hash-{source_item_id}",
        content_text=title,
        tags=["onenote"],
    )


def test_email_password_auth_session_and_logout(tmp_path: Path) -> None:
    client = create_feature_client(tmp_path)
    api_headers = {"X-RAG-API-Key": "test-rag-key"}

    register_response = client.post(
        "/api/v1/auth/register",
        headers=api_headers,
        json={
            "name": "Alex Morgan",
            "email": "alex@example.com",
            "password": "correct-horse-battery",
            "role": "Employee",
            "dept": "People",
        },
    )
    assert register_response.status_code == 200
    assert register_response.json()["status"] == "pending"

    pending_login = client.post(
        "/api/v1/auth/login",
        headers=api_headers,
        json={"email": "alex@example.com", "password": "correct-horse-battery"},
    )
    assert pending_login.status_code == 401

    admin_login = client.post(
        "/api/v1/auth/login",
        headers=api_headers,
        json={"email": "admin@example.com", "password": "admin-password-123"},
    )
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]
    users_response = client.get(
        "/api/v1/admin/users",
        headers={**api_headers, "Authorization": f"Bearer {admin_token}"},
    )
    alex = next(user for user in users_response.json() if user["email"] == "alex@example.com")
    approve_response = client.post(
        f"/api/v1/admin/users/{alex['user_id']}/approve",
        headers={**api_headers, "Authorization": f"Bearer {admin_token}"},
    )
    assert approve_response.status_code == 200

    login_response = client.post(
        "/api/v1/auth/login",
        headers=api_headers,
        json={"email": "alex@example.com", "password": "correct-horse-battery"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    me_response = client.get("/api/v1/auth/me", headers={**api_headers, "Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "alex@example.com"

    answer_response = client.post(
        "/api/v1/answer",
        headers={**api_headers, "Authorization": f"Bearer {token}"},
        json={
            "question": "What repository access do engineering teammates need?",
            "user_context": {"acl_tags": ["engineering"]},
        },
    )
    assert answer_response.status_code == 200
    assert answer_response.json()["citations"] == []

    logout_response = client.post("/api/v1/auth/logout", headers={**api_headers, "Authorization": f"Bearer {token}"})
    assert logout_response.status_code == 200
    assert logout_response.json() == {"success": True}

    expired_me = client.get("/api/v1/auth/me", headers={**api_headers, "Authorization": f"Bearer {token}"})
    assert expired_me.status_code == 401


def test_notebooks_and_documents_are_acl_filtered(tmp_path: Path) -> None:
    client = create_feature_client(tmp_path)
    headers = {"X-RAG-API-Key": "test-rag-key", "X-Acl-Tags": "public,employees"}

    notebooks = client.get("/api/v1/notebooks", headers=headers)
    documents = client.get("/api/v1/documents?sort=recently_updated&limit=5", headers=headers)

    assert notebooks.status_code == 200
    assert documents.status_code == 200
    notebook_titles = {notebook["title"] for notebook in notebooks.json()}
    document_titles = {document["title"] for document in documents.json()}
    assert "Onboarding" in notebook_titles
    assert "Engineering remote work guide" not in document_titles

    engineering_documents = client.get(
        "/api/v1/documents?sort=recently_updated&limit=5",
        headers={"X-RAG-API-Key": "test-rag-key", "X-Acl-Tags": "engineering"},
    )
    assert {document["title"] for document in engineering_documents.json()} == {"Engineering remote work guide"}


def test_document_detail_returns_raw_text_and_respects_acl(tmp_path: Path) -> None:
    client = create_feature_client(tmp_path)
    employee_headers = {"X-RAG-API-Key": "test-rag-key", "X-Acl-Tags": "public,employees"}

    documents = client.get("/api/v1/documents?sort=title&limit=5", headers=employee_headers)
    assert documents.status_code == 200
    document = next(item for item in documents.json() if item["source_item_id"] == "on-001")

    detail = client.get(
        "/api/v1/documents/detail",
        headers=employee_headers,
        params={"source_item_id": document["source_item_id"], "source_system": document["source_system"]},
    )
    assert detail.status_code == 200
    assert detail.json()["source_item_id"] == "on-001"
    assert "new hires should connect to the VPN" in detail.json()["content_text"]

    denied = client.get(
        "/api/v1/documents/detail",
        headers={"X-RAG-API-Key": "test-rag-key", "X-Acl-Tags": "engineering"},
        params={"source_item_id": "on-001", "source_system": "onenote"},
    )
    assert denied.status_code == 404

    wrong_source = client.get(
        "/api/v1/documents/detail",
        headers=employee_headers,
        params={"source_item_id": "on-001", "source_system": "sharepoint"},
    )
    assert wrong_source.status_code == 404


def test_trending_records_answer_questions_and_respects_acl(tmp_path: Path) -> None:
    client = create_feature_client(tmp_path)
    employee_headers = {"X-RAG-API-Key": "test-rag-key", "X-Acl-Tags": "public,employees"}

    for _ in range(2):
        response = client.post(
            "/api/v1/answer",
            headers=employee_headers,
            json={"question": "What should I do on day one?"},
        )
        assert response.status_code == 200

    trending = client.get("/api/v1/trending?window=30d&limit=5", headers=employee_headers)
    assert trending.status_code == 200
    assert trending.json()[0]["question"] == "What should I do on day one?"
    assert trending.json()[0]["count"] == 1
    assert trending.json()[0]["unique_users"] == 1

    hidden = client.get(
        "/api/v1/trending?window=30d&limit=5",
        headers={"X-RAG-API-Key": "test-rag-key", "X-Acl-Tags": "engineering"},
    )
    assert hidden.status_code == 200
    assert hidden.json() == []


def test_recent_documents_use_local_update_and_attachment_timestamps() -> None:
    page_old_source = _source_document(
        "Older OneNote page",
        source_item_id="onenote:old-page",
        last_modified_utc=datetime(2026, 5, 1, 9, 0, tzinfo=UTC),
        updated_at_utc=datetime(2026, 5, 1, 9, 5, tzinfo=UTC),
    )
    page_with_attachment = _source_document(
        "Page with new attachment",
        source_item_id="onenote:attachment-page",
        last_modified_utc=datetime(2026, 5, 2, 9, 0, tzinfo=UTC),
        updated_at_utc=datetime(2026, 5, 2, 9, 5, tzinfo=UTC),
    )
    page_locally_synced = _source_document(
        "Locally re-synced page",
        source_item_id="onenote:local-sync-page",
        last_modified_utc=datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        updated_at_utc=datetime(2026, 6, 5, 10, 0, tzinfo=UTC),
    )
    attachment = SourceAttachment(
        download_id="download-1",
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="notebook",
        parent_source_item_id=page_with_attachment.source_item_id,
        parent_title=page_with_attachment.title,
        source_url="https://example.test/attachment-page",
        resource_url="mock://resource",
        file_name="guide.zip",
        file_extension="zip",
        size_bytes=12,
        readable=False,
        storage_path="ab/download-1.zip",
        content_hash="hash",
        last_modified_utc=datetime(2026, 5, 2, 9, 0, tzinfo=UTC),
        updated_at_utc=datetime(2026, 6, 5, 11, 0, tzinfo=UTC),
        acl_tags=["employees"],
    )

    class Metadata:
        name = "test-metadata"

        def list_documents(self):
            return [page_old_source, page_with_attachment, page_locally_synced]

        def list_attachments(self, parent_source_item_ids=None):
            if parent_source_item_ids and attachment.parent_source_item_id not in parent_source_item_ids:
                return []
            return [attachment]

        def get_attachment(self, download_id: str):
            return attachment if download_id == attachment.download_id else None

    service = DocumentService(metadata=Metadata(), access_scope_resolver=AccessScopeResolver())
    documents = service.list_documents(UserContext(acl_tags=["employees"]), sort="recently_updated", limit=3)

    assert [document.title for document in documents] == [
        "Page with new attachment",
        "Locally re-synced page",
        "Older OneNote page",
    ]
    assert documents[0].updated_at_utc == attachment.updated_at_utc


def test_feedback_persists_and_is_queryable(tmp_path: Path) -> None:
    client = create_feature_client(tmp_path)
    headers = {"X-RAG-API-Key": "test-rag-key", "X-User-Id": "user-1", "X-Acl-Tags": "public,employees"}

    created = client.post(
        "/api/v1/feedback",
        headers=headers,
        json={
            "response_id": "resp-123",
            "conversation_id": "conv-123",
            "rating": "down",
            "flag_gap": True,
            "comment": "Need the missing policy.",
            "question": "Where is the missing policy?",
            "topic_id": "onboarding",
        },
    )
    assert created.status_code == 200
    assert created.json()["flag_gap"] is True

    listed = client.get("/api/v1/feedback", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["response_id"] == "resp-123"


def test_streaming_answer_emits_delta_and_final_payload(tmp_path: Path) -> None:
    client = create_feature_client(tmp_path)
    headers = {"X-RAG-API-Key": "test-rag-key", "X-Acl-Tags": "public,employees"}

    with client.stream(
        "POST",
        "/api/v1/answer/stream",
        headers=headers,
        json={"question": "What should I do on day one?"},
    ) as response:
        body = "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in response.iter_raw())

    assert response.status_code == 200
    assert "event: delta" in body
    assert "event: final" in body
    assert "Day 1 onboarding checklist" in body


def test_attachment_download_streams_file_and_respects_acl(tmp_path: Path) -> None:
    storage_root = tmp_path / "attachments"
    stored = storage_root / "ab" / "download-1.txt"
    stored.parent.mkdir(parents=True)
    stored.write_bytes(b"download me")
    settings = AppSettings(
        app_env="test",
        mock_api_key="test-key",
        rag_api_key="test-rag-key",
        retrieval_provider="mock",
        default_llm_provider="mock",
        default_model_name="mock-onboarding-assistant",
        security_audit_enabled=False,
        app_database_url=f"sqlite:///{tmp_path / 'app.sqlite'}",
        attachment_storage_dir=str(storage_root),
    )
    app = create_app(settings)
    attachment = SourceAttachment(
        download_id="download-1",
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="notebook",
        parent_source_item_id="onenote:page-1",
        parent_title="Setup",
        source_url="https://example.test/setup",
        resource_url="mock://resource",
        file_name="guide.txt",
        file_extension="txt",
        mime_type="text/plain",
        size_bytes=11,
        readable=True,
        indexed_source_item_id="onenote-attachment:download-1",
        storage_path="ab/download-1.txt",
        content_hash="hash",
        acl_tags=["employees"],
    )

    class FakeDocumentService:
        def get_attachment_for_download(self, user_context, *, download_id: str):
            if download_id == attachment.download_id and "employees" in user_context.acl_tags:
                return attachment
            return None

    app.dependency_overrides[get_document_service] = lambda: FakeDocumentService()
    client = TestClient(app)

    allowed = client.get(
        "/api/v1/attachments/download-1/download",
        headers={"X-RAG-API-Key": "test-rag-key", "X-Acl-Tags": "employees"},
    )
    denied = client.get(
        "/api/v1/attachments/download-1/download",
        headers={"X-RAG-API-Key": "test-rag-key", "X-Acl-Tags": "finance"},
    )

    assert allowed.status_code == 200
    assert allowed.content == b"download me"
    assert "guide.txt" in allowed.headers["content-disposition"]
    assert denied.status_code == 404

