from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

from rag_api.adapters.llm.mock import MockLlmAdapter
from rag_api.main import create_app
from rag_api.ports import RetrievalPort
from rag_api.services import AccessScopeResolver, AnswerService, PromptBuilder, TopicLoader, TopicService
from shared_schemas import (
    AccessScope,
    AnswerRequest,
    AppSettings,
    RetrievalMetadata,
    RetrievalRequest,
    RetrievalResult,
    UserContext,
)


def create_test_client() -> TestClient:
    settings = AppSettings(
        app_env="test",
        mock_api_key="test-key",
        rag_api_key="",
        retrieval_provider="mock",
        default_llm_provider="mock",
        default_model_name="mock-onboarding-assistant",
        security_audit_enabled=False,
    )
    return TestClient(create_app(settings))


def test_topics_endpoint_loads_public_topic_view() -> None:
    client = create_test_client()

    response = client.get("/api/v1/topics")
    payload = response.json()

    assert response.status_code == 200
    assert {topic["id"] for topic in payload}.issuperset({"project-deployment", "hr", "onboarding"})
    assert "acl_tags" not in payload[0]
    assert "retrieval_tags" not in payload[0]
    assert payload[0]["suggested_questions"]


def test_answer_endpoint_accepts_topic_id_and_returns_topic_suggestions() -> None:
    client = create_test_client()

    response = client.post(
        "/api/v1/answer",
        json={
            "topic_id": "onboarding",
            "question": "What should I do on day one?",
            "user_context": {"acl_tags": ["public", "employees"]},
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["retrieval_meta"]["topic_id"] == "onboarding"
    assert payload["suggested_questions"]
    assert "What should I do on day one?" in payload["suggested_questions"]


def test_answer_endpoint_uses_configured_default_acl_when_context_is_omitted() -> None:
    settings = AppSettings(
        app_env="test",
        mock_api_key="test-key",
        rag_api_key="",
        retrieval_provider="mock",
        default_llm_provider="mock",
        default_model_name="mock-onboarding-assistant",
        auth_default_acl_tags="engineering",
        security_audit_enabled=False,
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/v1/answer",
        json={
            "question": "What repository access do engineering teammates need?",
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["citations"]
    assert payload["citations"][0]["source_item_id"] == "on-003"
    assert payload["retrieval_meta"]["access_scope"]["allowed_acl_tags"] == ["engineering"]


def test_unknown_topic_id_returns_bad_request() -> None:
    client = create_test_client()

    response = client.post(
        "/api/v1/answer",
        json={
            "topic_id": "missing-topic",
            "question": "What should I do on day one?",
        },
    )

    assert response.status_code == 400
    assert "Unknown topic_id" in response.json()["detail"]


def test_topic_scope_narrows_acl_and_source_filters_before_retrieval(tmp_path) -> None:
    config_path = tmp_path / "topics.json"
    config_path.write_text(
        json.dumps(
            [
                {
                    "id": "engineering-deployment",
                    "name": "Engineering Deployment",
                    "description": "Engineering releases and rollback steps.",
                    "acl_tags": ["employees", "engineering"],
                    "source_filters": ["onenote", "sharepoint"],
                    "retrieval_tags": ["deployment", "release", "rollback"],
                    "suggested_questions": ["How do I deploy?"],
                }
            ]
        ),
        encoding="utf-8",
    )
    retriever = CapturingRetriever()
    service = AnswerService(
        llm=MockLlmAdapter("mock-onboarding-assistant"),
        prompt_builder=PromptBuilder(),
        retriever=retriever,
        access_scope_resolver=AccessScopeResolver(),
        reranker=None,
        topic_service=TopicService(TopicLoader(str(config_path))),
    )

    response = asyncio.run(
        service.answer(
            AnswerRequest(
                topic_id="engineering-deployment",
                question="How do I deploy?",
                user_context=UserContext(acl_tags=["public", "employees", "engineering"]),
                source_filters=["onenote", "confluence"],
            )
        )
    )

    captured_request = retriever.requests[0]
    assert response.suggested_questions == ["How do I deploy?"]
    assert captured_request.topic_id == "engineering-deployment"
    assert "deployment" in captured_request.question
    assert captured_request.access_scope is not None
    assert captured_request.access_scope.allowed_acl_tags == ["employees", "engineering"]
    assert captured_request.access_scope.source_filters == ["onenote"]


class CapturingRetriever(RetrievalPort):
    name = "capturing-retriever"

    def __init__(self) -> None:
        self.requests: list[RetrievalRequest] = []

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        self.requests.append(request)
        access_scope = request.access_scope or AccessScope(
            user_id=request.user_context.user_id,
            email=request.user_context.email,
            tenant_id=request.user_context.tenant_id,
            allowed_acl_tags=request.user_context.acl_tags,
            source_filters=request.source_filters,
        )
        return RetrievalResult(
            chunks=[],
            metadata=RetrievalMetadata(
                strategy=self.name,
                access_scope=access_scope,
                requested_top_k=request.top_k,
                candidate_count=0,
                returned_count=0,
                filtered_count=0,
                source_filters=access_scope.source_filters,
                collections_queried=[],
                payload_filter={},
                topic_id=request.topic_id,
                topic_tags=request.topic_tags,
            ),
        )

    async def ready(self) -> bool:
        return True
