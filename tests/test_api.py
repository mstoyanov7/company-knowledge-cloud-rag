from fastapi.testclient import TestClient

from rag_api.main import create_app
from shared_schemas import AppSettings


def create_test_client() -> TestClient:
    settings = AppSettings(
        app_env="test",
        mock_api_key="test-key",
        rag_api_key="",
        retrieval_provider="mock",
        default_model_name="mock-onboarding-assistant",
        security_audit_enabled=False,
    )
    return TestClient(create_app(settings))


def test_health_ready_and_version_endpoints() -> None:
    client = create_test_client()

    health_response = client.get("/health")
    ready_response = client.get("/ready")
    version_response = client.get("/version")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}

    assert ready_response.status_code == 200
    assert ready_response.json()["status"] == "ready"
    assert ready_response.json()["checks"] == {"llm": True, "retriever": True}

    assert version_response.status_code == 200
    assert version_response.json()["environment"] == "test"


def test_answer_endpoint_returns_answer_and_citations() -> None:
    client = create_test_client()

    response = client.post(
        "/api/v1/answer",
        json={
            "question": "What should I do on day one?",
            "user_context": {"acl_tags": ["public", "employees"]},
        },
    )

    payload = response.json()

    assert response.status_code == 200
    assert "answer" in payload
    assert payload["citations"]
    assert "retrieval_meta" in payload
    assert payload["metadata"]["retrieved_chunk_count"] >= 1


def test_answer_endpoint_excludes_unauthorized_content() -> None:
    client = create_test_client()

    response = client.post(
        "/api/v1/answer",
        json={
            "question": "incident repository production",
            "user_context": {"acl_tags": ["public", "employees"]},
        },
    )

    payload = response.json()

    assert response.status_code == 200
    assert payload["metadata"]["retrieved_chunk_count"] == 0
    assert payload["citations"] == []
    assert payload["retrieval_meta"]["filtered_count"] >= 1


def test_answer_endpoint_allows_authorized_content_and_maps_citations() -> None:
    client = create_test_client()

    response = client.post(
        "/api/v1/answer",
        json={
            "question": "What repository access do engineering teammates need?",
            "user_context": {"acl_tags": ["engineering"]},
        },
    )

    payload = response.json()
    citation = payload["citations"][0]

    assert response.status_code == 200
    assert payload["metadata"]["retrieved_chunk_count"] == 1
    assert citation["source_item_id"] == "sp-002"
    assert citation["chunk_index"] == 0
    assert citation["source_system"] == "sharepoint"
    assert citation["source_url"].endswith("/remote-work")
    assert citation["title"] == "Engineering remote work guide"


def test_openai_compatible_chat_completion_and_models() -> None:
    client = create_test_client()
    headers = {"Authorization": "Bearer test-key"}

    models_response = client.get("/v1/models", headers=headers)
    completion_response = client.post(
        "/v1/chat/completions",
        headers=headers,
        json={
            "model": "mock-onboarding-assistant",
            "messages": [
                {"role": "user", "content": "What benefits should I review during onboarding?"}
            ],
        },
    )

    assert models_response.status_code == 200
    assert models_response.json()["data"][0]["id"] == "mock-onboarding-assistant"

    assert completion_response.status_code == 200
    assert completion_response.json()["choices"][0]["message"]["content"]
    assert completion_response.json()["citations"]


def test_openai_compatible_streaming_chat_completion() -> None:
    client = create_test_client()
    headers = {"Authorization": "Bearer test-key"}

    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers=headers,
        json={
            "model": "mock-onboarding-assistant",
            "stream": True,
            "messages": [
                {"role": "user", "content": "What should engineering teammates request during onboarding?"}
            ],
        },
    ) as response:
        body = "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in response.iter_raw())

    assert response.status_code == 200
    assert "chat.completion.chunk" in body
    assert "[DONE]" in body
