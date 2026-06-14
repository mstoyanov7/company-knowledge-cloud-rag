from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from rag_api.adapters.llm.mock import MockLlmAdapter
from rag_api.main import create_app
from rag_api.persistence.app_store import AppDataStore
from rag_api.ports import RetrievalPort
from rag_api.services import AccessScopeResolver, AnswerService, PromptBuilder, TopicLoader, TopicService
from rag_api.services.topic_sync import reconcile_topics_from_sources
from shared_schemas import (
    AccessScope,
    AnswerMetadata,
    AnswerRequest,
    AnswerResponse,
    AppSettings,
    Citation,
    RetrievalMetadata,
    RetrievalRequest,
    RetrievalResult,
    SourceDocument,
    SourceAttachment,
    UserContext,
)


def create_test_client(tmp_path: Path) -> TestClient:
    settings = AppSettings(
        app_env="test",
        app_database_url=f"sqlite:///{tmp_path / 'rag-api.sqlite3'}",
        mock_api_key="test-key",
        rag_api_key="",
        retrieval_provider="mock",
        default_llm_provider="mock",
        default_model_name="mock-onboarding-assistant",
        security_audit_enabled=False,
    )
    return TestClient(create_app(settings))


def test_topics_endpoint_loads_public_topic_view(tmp_path: Path) -> None:
    client = create_test_client(tmp_path)

    response = client.get("/api/v1/topics")
    payload = response.json()

    assert response.status_code == 200
    assert {topic["id"] for topic in payload} == {"section-benefits", "section-first-day", "section-handbook"}
    assert "acl_tags" not in payload[0]
    assert "retrieval_tags" not in payload[0]
    assert "section_filters" not in payload[0]


def test_answer_endpoint_accepts_section_topic_id_and_filters_retrieval(tmp_path: Path) -> None:
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/v1/answer",
        json={
            "topic_id": "section-first-day",
            "question": "What should I do on day one?",
            "user_context": {"acl_tags": ["public", "employees"]},
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["retrieval_meta"]["topic_id"] == "section-first-day"
    assert payload["retrieval_meta"]["section_filters"] == ["First day"]
    assert {citation["metadata"]["section_name"] for citation in payload["citations"]} == {"First day"}


def test_answer_endpoint_uses_configured_default_acl_when_context_is_omitted(tmp_path: Path) -> None:
    settings = AppSettings(
        app_env="test",
        app_database_url=f"sqlite:///{tmp_path / 'rag-api.sqlite3'}",
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


def test_unknown_topic_id_returns_bad_request(tmp_path: Path) -> None:
    client = create_test_client(tmp_path)

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
                    "section_filters": ["Release Management"],
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
    assert captured_request.section_filters == ["Release Management"]


def test_reconcile_topics_from_sources_creates_preserves_and_disables(tmp_path) -> None:
    settings = AppSettings(
        app_env="test",
        app_database_url=f"sqlite:///{tmp_path / 'app.sqlite'}",
        auth_default_acl_tags="public",
    )
    store = AppDataStore(settings)
    store.ensure_schema()

    reconcile_topics_from_sources(
        _StaticMetadata(
            [
                _source_document("hr-1", "HR Questions", ["employees"]),
                _source_document("hr-2", "HR Questions", ["finance"]),
                _source_document("temp-1", "Temporary", ["employees"]),
            ]
        ),
        store,
        settings,
    )

    by_section = {record.section_key: record for record in store.list_topic_records(enabled_only=False)}
    hr = by_section["HR Questions"]
    assert hr.topic_id == "section-hr-questions"
    assert hr.icon == "users-round"
    assert json.loads(hr.acl_tags_json) == ["employees", "finance"]
    assert json.loads(hr.section_filters_json) == ["HR Questions"]
    assert hr.auto_managed is True
    assert hr.enabled is True

    store.upsert_topic_record(
        hr.topic_id,
        {"name": "People Ops"},
        updated_by_user_id="admin-1",
    )

    reconcile_topics_from_sources(
        _StaticMetadata(
            [
                _source_document("hr-3", "HR Questions", ["engineering"]),
                _source_document("it-1", "IT Support", []),
            ]
        ),
        store,
        settings,
    )

    by_section = {record.section_key: record for record in store.list_topic_records(enabled_only=False)}
    assert by_section["HR Questions"].name == "People Ops"
    assert json.loads(by_section["HR Questions"].acl_tags_json) == ["employees", "finance"]
    assert by_section["HR Questions"].enabled is True
    # The "Temporary" section is gone and its topic was purely sync-managed, so
    # it is deleted rather than left behind as a disabled duplicate.
    assert "Temporary" not in by_section
    assert by_section["IT Support"].icon == "life-buoy"
    assert json.loads(by_section["IT Support"].acl_tags_json) == ["public"]


def test_reconcile_disables_but_keeps_human_edited_topic_for_removed_section(tmp_path) -> None:
    settings = AppSettings(
        app_env="test",
        app_database_url=f"sqlite:///{tmp_path / 'app.sqlite'}",
        auth_default_acl_tags="public",
    )
    store = AppDataStore(settings)
    store.ensure_schema()

    reconcile_topics_from_sources(
        _StaticMetadata([_source_document("temp-1", "Temporary", ["employees"])]),
        store,
        settings,
    )
    temp = {r.section_key: r for r in store.list_topic_records(enabled_only=False)}["Temporary"]
    store.upsert_topic_record(temp.topic_id, {"name": "Temporary (curated)"}, updated_by_user_id="admin-1")

    reconcile_topics_from_sources(
        _StaticMetadata([_source_document("it-1", "IT Support", [])]),
        store,
        settings,
    )

    by_id = {r.topic_id: r for r in store.list_topic_records(enabled_only=False)}
    # Human edits are preserved, but the topic is hidden since its section is gone.
    assert by_id[temp.topic_id].name == "Temporary (curated)"
    assert by_id[temp.topic_id].enabled is False


def test_reconcile_can_skip_stale_pruning_for_partial_source_views(tmp_path) -> None:
    settings = AppSettings(
        app_env="test",
        app_database_url=f"sqlite:///{tmp_path / 'app.sqlite'}",
        auth_default_acl_tags="public",
    )
    store = AppDataStore(settings)
    store.ensure_schema()

    reconcile_topics_from_sources(
        _StaticMetadata(
            [
                _source_document("hr-1", "HR Questions", ["employees"]),
                _source_document("it-1", "IT Support", ["employees"]),
            ]
        ),
        store,
        settings,
    )

    reconcile_topics_from_sources(
        _StaticMetadata([_source_document("hr-2", "HR Questions", ["employees"])]),
        store,
        settings,
        prune_stale=False,
    )

    sections = {record.section_key for record in store.list_topic_records(enabled_only=False)}
    assert sections == {"HR Questions", "IT Support"}


def test_topic_service_can_load_without_pruning_seed_topics(tmp_path) -> None:
    settings = AppSettings(
        app_env="test",
        app_database_url=f"sqlite:///{tmp_path / 'app.sqlite'}",
        auth_default_acl_tags="public",
    )
    store = AppDataStore(settings)
    store.ensure_schema()
    store.upsert_topic_record("old-seed", {"name": "Old Seed"}, updated_by_user_id="seed")

    empty_config = tmp_path / "topics.json"
    empty_config.write_text("[]", encoding="utf-8")
    TopicService(loader=TopicLoader(str(empty_config)), store=store, prune_orphaned_seed_topics=False)

    ids = {record.topic_id for record in store.list_topic_records(enabled_only=False)}
    assert "old-seed" in ids


def test_topic_service_prunes_orphaned_seed_topics(tmp_path) -> None:
    settings = AppSettings(
        app_env="test",
        app_database_url=f"sqlite:///{tmp_path / 'app.sqlite'}",
        auth_default_acl_tags="public",
    )
    store = AppDataStore(settings)
    store.ensure_schema()
    # A legacy seed/cleanup topic from a previous config, plus a real admin topic.
    store.upsert_topic_record("old-seed", {"name": "Old Seed"}, updated_by_user_id="topic-cleanup")
    store.upsert_topic_record("admin-made", {"name": "Admin Made"}, updated_by_user_id="admin-1")

    empty_config = tmp_path / "topics.json"
    empty_config.write_text("[]", encoding="utf-8")
    TopicService(loader=TopicLoader(str(empty_config)), store=store)

    ids = {record.topic_id for record in store.list_topic_records(enabled_only=False)}
    assert "old-seed" not in ids  # legacy seed pruned because config no longer defines it
    assert "admin-made" in ids  # admin-created topics are preserved


def test_app_topic_compat_columns_are_added_to_old_sqlite_db(tmp_path) -> None:
    db_path = tmp_path / "old.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE app_topics (
                topic_id VARCHAR(120) PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                description TEXT NOT NULL,
                icon VARCHAR(80),
                acl_tags_json TEXT NOT NULL,
                source_filters_json TEXT NOT NULL,
                retrieval_tags_json TEXT NOT NULL,
                suggested_questions_json TEXT NOT NULL,
                enabled BOOLEAN NOT NULL,
                created_at_utc DATETIME NOT NULL,
                updated_at_utc DATETIME NOT NULL,
                updated_by_user_id VARCHAR(64)
            )
            """
        )

    settings = AppSettings(app_env="test", app_database_url=f"sqlite:///{db_path}")
    store = AppDataStore(settings)
    store.ensure_schema()

    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(app_topics)")}

    assert {"section_filters_json", "section_key", "auto_managed"}.issubset(columns)


def _canned_response(answer: str, *, with_citation: bool, suggested: list[str] | None = None) -> AnswerResponse:
    access_scope = AccessScope(
        user_id="u1", email="u1@example.com", tenant_id="local-tenant", allowed_acl_tags=["public"], source_filters=[]
    )
    citations = []
    if with_citation:
        citations = [
            Citation(
                index=1,
                chunk_id="c1",
                source_item_id="s1",
                chunk_index=0,
                title="Git Branching and Pull Request Workflow",
                source_system="onenote",
                source_container="notebook",
                source_url="onenote://s1",
                snippet="Git Workflow Cheat Sheet",
                last_modified_utc=datetime(2026, 6, 1, tzinfo=UTC),
            )
        ]
    return AnswerResponse(
        answer=answer,
        citations=citations,
        retrieval_meta=RetrievalMetadata(
            strategy="test",
            access_scope=access_scope,
            requested_top_k=3,
            candidate_count=0,
            returned_count=len(citations),
            filtered_count=0,
            source_filters=[],
            section_filters=[],
            collections_queried=[],
            payload_filter={},
        ),
        metadata=AnswerMetadata(
            provider="mock",
            model="mock",
            retrieval_strategy="test",
            retrieved_chunk_count=len(citations),
            source_systems=["onenote"],
            duration_ms=1,
        ),
        suggested_questions=suggested or [],
    )


def _service_for_fallback(tmp_path: Path) -> AnswerService:
    config_path = tmp_path / "topics.json"
    config_path.write_text(
        json.dumps(
            [{"id": "eng", "name": "Engineering Handbook", "description": "d", "section_filters": ["Engineering Handbook"]}]
        ),
        encoding="utf-8",
    )
    return AnswerService(
        llm=MockLlmAdapter("mock-onboarding-assistant"),
        prompt_builder=PromptBuilder(),
        retriever=CapturingRetriever(),
        access_scope_resolver=AccessScopeResolver(),
        reranker=None,
        topic_service=TopicService(TopicLoader(str(config_path))),
    )


def test_answer_widens_across_topics_when_scoped_search_is_empty(tmp_path: Path) -> None:
    service = _service_for_fallback(tmp_path)
    primary = _canned_response(
        "I could not find that information in the available OneNote notes or readable attachments.",
        with_citation=False,
        suggested=["Ask about onboarding"],
    )
    fallback = _canned_response("### Git Workflow Cheat Sheet\n- Trunk-based development", with_citation=True)

    calls: list[bool] = []

    async def fake_answer_once(request, *, allow_clarification=True, ignore_topic=False):
        calls.append(ignore_topic)
        return fallback if ignore_topic else primary

    service._answer_once = fake_answer_once  # type: ignore[method-assign]

    response = asyncio.run(
        service.answer(AnswerRequest(topic_id="eng", question="is there any git workflow cheat sheet"))
    )

    assert calls == [False, True]  # scoped first, then global fallback
    assert "couldn't find this in **Engineering Handbook**" in response.answer
    assert "Trunk-based development" in response.answer
    assert response.citations  # carried from the global answer
    assert response.suggested_questions == ["Ask about onboarding"]  # carried from the scoped pass


def test_answer_keeps_scoped_answer_when_it_is_confident(tmp_path: Path) -> None:
    service = _service_for_fallback(tmp_path)
    confident = _canned_response("### Day one\n- Orientation at 9am", with_citation=True)

    calls: list[bool] = []

    async def fake_answer_once(request, *, allow_clarification=True, ignore_topic=False):
        calls.append(ignore_topic)
        return confident

    service._answer_once = fake_answer_once  # type: ignore[method-assign]

    response = asyncio.run(service.answer(AnswerRequest(topic_id="eng", question="what happens on day one")))

    assert calls == [False]  # no fallback when the scoped answer is already confident
    assert "couldn't find this in" not in response.answer


def test_answer_does_not_widen_without_a_selected_topic(tmp_path: Path) -> None:
    service = _service_for_fallback(tmp_path)
    no_info = _canned_response(
        "I could not find that information in the available OneNote notes or readable attachments.",
        with_citation=False,
    )

    calls: list[bool] = []

    async def fake_answer_once(request, *, allow_clarification=True, ignore_topic=False):
        calls.append(ignore_topic)
        return no_info

    service._answer_once = fake_answer_once  # type: ignore[method-assign]

    response = asyncio.run(service.answer(AnswerRequest(question="is there any git workflow cheat sheet")))

    assert calls == [False]  # no topic selected, so nothing to widen from
    assert response.answer.startswith("I could not find")


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
                section_filters=request.section_filters,
                collections_queried=[],
                payload_filter={},
                topic_id=request.topic_id,
                topic_tags=request.topic_tags,
            ),
        )

    async def ready(self) -> bool:
        return True


class _StaticMetadata:
    name = "static-metadata"

    def __init__(self, documents: list[SourceDocument]) -> None:
        self._documents = documents

    def list_documents(self) -> list[SourceDocument]:
        return self._documents

    def list_attachments(self, parent_source_item_ids: list[str] | None = None) -> list[SourceAttachment]:
        return []

    def get_attachment(self, download_id: str) -> SourceAttachment | None:
        return None


def _source_document(source_item_id: str, section_name: str, acl_tags: list[str]) -> SourceDocument:
    return SourceDocument(
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="notebook",
        source_item_id=source_item_id,
        source_url=f"onenote://{source_item_id}",
        title=f"{section_name} page",
        file_name=f"{source_item_id}.one",
        file_extension="one",
        section_path=f"Notebook / {section_name}",
        last_modified_utc=datetime(2026, 6, 1, tzinfo=UTC),
        acl_tags=acl_tags,
        content_hash=source_item_id,
        content_text="content",
        metadata={"section_name": section_name},
    )
