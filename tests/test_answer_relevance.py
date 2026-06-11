from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from rag_api.adapters.llm.mock import MockLlmAdapter
from rag_api.services import AccessScopeResolver, AnswerService, PromptBuilder
from rag_api.services.query_understanding import analyze_question
from shared_schemas import (
    AccessScope,
    AppSettings,
    ChunkDocument,
    RetrievalMetadata,
    RetrievalRequest,
    RetrievalResult,
    SourceDocument,
    SourceAttachment,
    UserContext,
)

NO_INFORMATION_ANSWER = "I could not find that information in the available OneNote notes or readable attachments."


class StaticRetriever:
    name = "static"

    def __init__(self, chunks: list[ChunkDocument]) -> None:
        self.chunks = chunks

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        access_scope = request.access_scope or AccessScope(
            user_id=request.user_context.user_id,
            email=request.user_context.email,
            tenant_id=request.user_context.tenant_id,
            allowed_acl_tags=request.user_context.acl_tags,
        )
        return RetrievalResult(
            chunks=self.chunks,
            metadata=RetrievalMetadata(
                strategy=self.name,
                access_scope=access_scope,
                requested_top_k=request.top_k,
                candidate_count=len(self.chunks),
                returned_count=len(self.chunks),
                filtered_count=0,
            ),
        )

    async def ready(self) -> bool:
        return True


class StaticMetadata:
    name = "static-metadata"

    def __init__(self, documents: list[SourceDocument], attachments: list[SourceAttachment] | None = None) -> None:
        self.documents = documents
        self.attachments = attachments or []

    def list_documents(self) -> list[SourceDocument]:
        return list(self.documents)

    def list_attachments(self, parent_source_item_ids: list[str] | None = None) -> list[SourceAttachment]:
        if parent_source_item_ids is None:
            return list(self.attachments)
        parents = set(parent_source_item_ids)
        return [attachment for attachment in self.attachments if attachment.parent_source_item_id in parents]

    def get_attachment(self, download_id: str) -> SourceAttachment | None:
        return None


class QueryAwareRetriever:
    name = "query-aware"

    def __init__(self, chunk: ChunkDocument) -> None:
        self.chunk = chunk
        self.queries: list[str] = []

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        self.queries.append(request.question)
        access_scope = request.access_scope or AccessScope(
            user_id=request.user_context.user_id,
            email=request.user_context.email,
            tenant_id=request.user_context.tenant_id,
            allowed_acl_tags=request.user_context.acl_tags,
        )
        chunks = []
        if "diploma work" in request.question or "research focus" in request.question:
            chunks = [self.chunk.model_copy(update={"score": 10.0})]
        return RetrievalResult(
            chunks=chunks,
            metadata=RetrievalMetadata(
                strategy=self.name,
                access_scope=access_scope,
                requested_top_k=request.top_k,
                candidate_count=len(chunks),
                returned_count=len(chunks),
                filtered_count=0,
            ),
        )

    async def ready(self) -> bool:
        return True


class StaticLlm:
    provider_name = "static"
    model_name = "static"

    def __init__(self, answer_text: str) -> None:
        self.answer_text = answer_text

    async def generate(self, prompt):
        from rag_api.ports import GenerationResult

        return GenerationResult(
            provider=self.provider_name,
            model=self.model_name,
            answer_text=self.answer_text,
        )

    async def ready(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return [self.model_name]


class StaticQueryPlanner:
    def __init__(self, analysis) -> None:
        self.analysis = analysis

    async def plan(self, question: str):
        return self.analysis


def _planned_analysis(
    question: str,
    *,
    semantic_queries: tuple[str, ...],
    keyword_queries: tuple[str, ...] = (),
    important_entities: tuple[str, ...] = (),
):
    base = analyze_question(question)
    return replace(
        base,
        important_entities=important_entities or base.important_entities,
        rewritten_question=semantic_queries[0] if semantic_queries else base.rewritten_question,
        semantic_queries=semantic_queries,
        keyword_queries=keyword_queries or base.keyword_queries,
    )


def _chunk(text: str, *, title: str = "Travel notes", chunk_id: str | None = None) -> ChunkDocument:
    return ChunkDocument(
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="onenote",
        source_item_id=f"onenote:{chunk_id or title}",
        source_url="https://example.test",
        title=title,
        section_path="Notes",
        last_modified_utc=datetime(2026, 4, 26, tzinfo=UTC),
        acl_tags=["employees"],
        content_hash="hash",
        chunk_id=chunk_id or "chunk-1",
        chunk_index=0,
        chunk_text=text,
        embedding_model="token-hash-v1",
    )


def _readable_attachment_chunk(
    text: str,
    *,
    parent_source_item_id: str,
    parent_title: str,
    file_name: str,
    chunk_id: str = "attachment-chunk",
) -> ChunkDocument:
    return _chunk(text, title=f"{parent_title} - {file_name}", chunk_id=chunk_id).model_copy(
        update={
            "source_item_id": f"onenote-attachment:{file_name}",
            "source_url": f"/api/v1/attachments/download-{file_name}/download",
            "chunk_id": chunk_id,
            "metadata": {
                "document_kind": "attachment",
                "download_id": f"download-{file_name}",
                "download_url": f"/api/v1/attachments/download-{file_name}/download",
                "readable": True,
                "indexed_source_item_id": f"onenote-attachment:{file_name}",
                "parent_source_item_id": parent_source_item_id,
                "parent_title": parent_title,
                "parent_source_url": "https://example.test/page-abc",
                "attachment_file_name": file_name,
                "attachment_file_extension": file_name.rsplit(".", maxsplit=1)[-1],
            },
        }
    )


def _source_document(
    title: str,
    *,
    section_path: str,
    source_item_id: str | None = None,
    acl_tags: list[str] | None = None,
    content_text: str = "",
) -> SourceDocument:
    section_name = section_path.rsplit("/", maxsplit=1)[-1].strip()
    return SourceDocument(
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="onenote",
        source_item_id=source_item_id or f"onenote:{title}",
        source_url=f"https://example.test/{title.replace(' ', '-').lower()}",
        title=title,
        file_name=f"{title}.one",
        file_extension="one",
        mime_type="text/html",
        section_path=section_path,
        last_modified_utc=datetime(2026, 4, 26, tzinfo=UTC),
        acl_tags=acl_tags or ["employees"],
        content_hash="hash",
        content_text=content_text,
        tags=[],
        metadata={"section_name": section_name, "notebook_name": "Cloud-RAG"},
    )


def _attachment(
    file_name: str,
    *,
    parent_source_item_id: str,
    parent_title: str,
    download_id: str | None = None,
) -> SourceAttachment:
    extension = file_name.rsplit(".", maxsplit=1)[-1].lower() if "." in file_name else ""
    resolved_download_id = download_id or f"download-{file_name}"
    return SourceAttachment(
        download_id=resolved_download_id,
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="onenote",
        parent_source_item_id=parent_source_item_id,
        parent_title=parent_title,
        source_url="https://example.test/page",
        resource_url=f"https://example.test/{file_name}",
        file_name=file_name,
        file_extension=extension,
        mime_type="application/octet-stream",
        size_bytes=12,
        readable=False,
        storage_path=f"ab/{resolved_download_id}.{extension}",
        content_hash=f"hash-{resolved_download_id}",
        last_modified_utc=datetime(2026, 4, 26, tzinfo=UTC),
        acl_tags=["employees"],
    )


async def _answer_for(question: str, chunk: ChunkDocument):
    service = AnswerService(
        llm=MockLlmAdapter("mock"),
        prompt_builder=PromptBuilder(),
        retriever=StaticRetriever([chunk]),
        access_scope_resolver=AccessScopeResolver(),
        min_keyword_overlap=1,
    )
    from shared_schemas import AnswerRequest

    return await service.answer(
        AnswerRequest(
            question=question,
            user_context=UserContext(acl_tags=["employees"]),
            source_filters=["onenote"],
        )
    )


async def _answer_with_static_llm(question: str, chunk: ChunkDocument, answer_text: str, *, query_planner=None):
    return await _answer_with_static_llm_for_chunks(question, [chunk], answer_text, query_planner=query_planner)


async def _answer_with_static_llm_for_chunks(
    question: str,
    chunks: list[ChunkDocument],
    answer_text: str,
    *,
    query_planner=None,
):
    service = AnswerService(
        llm=StaticLlm(answer_text),
        prompt_builder=PromptBuilder(),
        retriever=StaticRetriever(chunks),
        access_scope_resolver=AccessScopeResolver(),
        min_keyword_overlap=1,
        query_planner=query_planner,
    )
    from shared_schemas import AnswerRequest

    return await service.answer(
        AnswerRequest(
            question=question,
            user_context=UserContext(acl_tags=["employees"]),
            source_filters=["onenote"],
        )
    )


def test_inventory_count_uses_page_titles_from_matching_section() -> None:
    import asyncio

    service = AnswerService(
        llm=StaticLlm("This should not be used."),
        prompt_builder=PromptBuilder(),
        retriever=StaticRetriever([]),
        metadata=StaticMetadata(
            [
                _source_document("Customer Portal Upgrade", section_path="Cloud-RAG / Project Setups"),
                _source_document("Warehouse Scanner Rollout", section_path="Cloud-RAG / Project Setups"),
                _source_document("Code of Conduct", section_path="Cloud-RAG / Company Policies"),
            ]
        ),
        access_scope_resolver=AccessScopeResolver(),
    )
    from shared_schemas import AnswerRequest

    response = asyncio.run(
        service.answer(
            AnswerRequest(
                question="How many projects are available in the company?",
                user_context=UserContext(acl_tags=["employees"]),
                source_filters=["onenote"],
            )
        )
    )

    assert response.retrieval_meta.strategy == "metadata-inventory"
    assert "There are 2 accessible projects in Project Setups." in response.answer
    assert "Customer Portal Upgrade" in response.answer
    assert "Warehouse Scanner Rollout" in response.answer
    assert [citation.title for citation in response.citations] == [
        "Customer Portal Upgrade",
        "Warehouse Scanner Rollout",
    ]


def test_inventory_count_respects_acl_tags() -> None:
    import asyncio

    service = AnswerService(
        llm=StaticLlm("This should not be used."),
        prompt_builder=PromptBuilder(),
        retriever=StaticRetriever([]),
        metadata=StaticMetadata(
            [
                _source_document("Public Project", section_path="Cloud-RAG / Project Setups"),
                _source_document(
                    "Finance Migration",
                    section_path="Cloud-RAG / Project Setups",
                    acl_tags=["finance"],
                ),
            ]
        ),
        access_scope_resolver=AccessScopeResolver(),
    )
    from shared_schemas import AnswerRequest

    response = asyncio.run(
        service.answer(
            AnswerRequest(
                question="How many projects are available in the company?",
                user_context=UserContext(acl_tags=["employees"]),
                source_filters=["onenote"],
            )
        )
    )

    assert "There is 1 accessible project in Project Setups." in response.answer
    assert [citation.title for citation in response.citations] == ["Public Project"]


def test_answer_service_returns_no_information_for_irrelevant_retrieval_hit() -> None:
    import asyncio

    response = asyncio.run(
        _answer_for(
            "What is the company vacation policy?",
            _chunk("Install Docker Desktop and configure Git credentials.", title="Developer setup"),
        )
    )

    assert response.answer == NO_INFORMATION_ANSWER
    assert response.citations == []
    assert response.metadata.retrieved_chunk_count == 0


def test_answer_service_keeps_relevant_onenote_hit() -> None:
    import asyncio

    response = asyncio.run(
        _answer_for(
            "How do I configure Docker?",
            _chunk("Install Docker Desktop and configure Git credentials.", title="Developer setup"),
        )
    )

    assert response.answer != NO_INFORMATION_ANSWER
    assert response.citations
    assert response.metadata.retrieved_chunk_count == 1


def test_answer_service_falls_back_to_extract_when_model_output_is_uncited() -> None:
    import asyncio

    response = asyncio.run(
        _answer_with_static_llm(
            "How do I configure Docker?",
            _chunk("Install Docker Desktop and configure Git credentials.", title="Developer setup"),
            "You should install Docker Desktop.",
        )
    )

    assert response.answer == (
        "### Developer setup\n\n"
        "- Install Docker Desktop and configure Git credentials"
    )
    assert response.citations


def test_answer_service_repairs_uncited_grounded_descriptive_answer() -> None:
    import asyncio

    response = asyncio.run(
        _answer_with_static_llm(
            "How do I configure Docker?",
            _chunk(
                "Install Docker Desktop from the onboarding package. "
                "After installation, sign in and configure Git credentials.",
                title="Developer setup",
            ),
            (
                "To configure Docker, install Docker Desktop from the onboarding package, "
                "then sign in and configure Git credentials."
            ),
        )
    )

    assert response.answer == (
        "### Developer setup\n\n"
        "To configure Docker, install Docker Desktop from the onboarding package, "
        "then sign in and configure Git credentials."
    )
    assert response.citations


def test_answer_service_falls_back_to_extract_when_model_output_has_unsupported_claims() -> None:
    import asyncio

    response = asyncio.run(
        _answer_with_static_llm(
            "How do I configure Docker?",
            _chunk("Install Docker Desktop and configure Git credentials.", title="Developer setup"),
            "Install Docker Desktop, then configure Kubernetes clusters and Terraform cloud workspaces. [1]",
        )
    )

    assert response.answer == (
        "### Developer setup\n\n"
        "- Install Docker Desktop and configure Git credentials"
    )
    assert response.citations


def test_answer_service_extracts_question_matching_sentence_from_mixed_chunk() -> None:
    import asyncio

    response = asyncio.run(
        _answer_with_static_llm(
            "How do I configure Docker?",
            _chunk(
                "Benefits include medical insurance and wellness budgets. "
                "Install Docker Desktop and configure Git credentials.",
                title="Developer setup",
            ),
            "You should review medical insurance and wellness budgets. [1]",
        )
    )

    assert response.answer == (
        "### Developer setup\n\n"
        "- Install Docker Desktop and configure Git credentials"
    )
    assert response.citations


def test_answer_service_replaces_title_only_model_answer_with_body_content() -> None:
    import asyncio

    response = asyncio.run(
        _answer_with_static_llm(
            "What should I do for Docker setup?",
            _chunk(
                "# Docker setup\n"
                "Run the Docker Desktop installer from the onboarding package.\n"
                "After installation, sign in and configure Git credentials.",
                title="Docker setup",
            ),
            "Docker setup [1]",
        )
    )

    assert response.answer == (
        "### Docker setup\n\n"
        "- Run the Docker Desktop installer from the onboarding package\n"
        "- After installation, sign in and configure Git credentials"
    )
    assert response.citations


def test_answer_service_prefers_working_hours_values_over_topic_mention() -> None:
    import asyncio

    response = asyncio.run(
        _answer_with_static_llm_for_chunks(
            "Whate are the working hours?",
            [
                _chunk(
                    "Employees must be available on Slack during working hours.",
                    title="Slack availability",
                    chunk_id="slack",
                ),
                _chunk(
                    "# Working Hours\n"
                    "Standard working hours: 09:00 - 18:00 (Monday-Friday)\n"
                    "Flexible start: 08:00 - 10:00 (must complete 8 hours)\n"
                    "Lunch break: 1 hour (unpaid)\n"
                    "Overtime requires manager approval",
                    title="Working Hours",
                    chunk_id="working-hours",
                ),
            ],
            "Employees must be available on Slack during working hours [1].",
        )
    )

    assert response.answer.startswith("### Working Hours")
    assert "- **Standard working hours:** 09:00 - 18:00 (Monday-Friday)" in response.answer
    assert "- **Flexible start:** 08:00 - 10:00 (must complete 8 hours)" in response.answer
    assert "- **Lunch break:** 1 hour (unpaid)" in response.answer
    assert "Overtime" not in response.answer
    assert "09:00" in response.answer
    assert "18:00" in response.answer
    assert "Slack" not in response.answer
    assert response.citations[0].title == "Working Hours"


def test_answer_service_rejects_working_hours_reference_without_hours_definition() -> None:
    import asyncio

    response = asyncio.run(
        _answer_with_static_llm(
            "what are the working hours",
            _chunk(
                "Employees must be available on Slack during working hours.",
                title="HR Policies",
            ),
            "Employees must be available on Slack during working hours [1].",
        )
    )

    assert response.answer == NO_INFORMATION_ANSWER
    assert response.citations == []


def test_answer_service_expands_too_narrow_structured_model_answer() -> None:
    import asyncio

    response = asyncio.run(
        _answer_with_static_llm(
            "What are the working hours?",
            _chunk(
                "# Working Hours\n"
                "Standard working hours: 09:00 - 18:00 (Monday-Friday)\n"
                "Flexible start: 08:00 - 10:00 (must complete 8 hours)\n"
                "Lunch break: 1 hour (unpaid)\n"
                "Overtime requires manager approval",
                title="Working Hours",
            ),
            "Standard working hours are 09:00 - 18:00 [1].",
        )
    )

    assert response.answer.startswith("### Working Hours")
    assert "- **Standard working hours:** 09:00 - 18:00 (Monday-Friday)" in response.answer
    assert "- **Flexible start:** 08:00 - 10:00 (must complete 8 hours)" in response.answer
    assert "- **Lunch break:** 1 hour (unpaid)" in response.answer


def test_answer_service_expands_full_first_day_schedule_across_chunks() -> None:
    import asyncio

    source_item_id = "onenote:first-day-orientation"
    chunks = [
        _chunk(
            "# Onboarding - 02 First Day Orientation\n"
            "Section: Onboarding\n"
            "Owner: HR Onboarding Team\n"
            "Summary: First-day onboarding guide covering welcome session and agenda.",
            title="First Day Orientation",
            chunk_id="first-day-metadata",
        ).model_copy(
            update={
                "source_item_id": source_item_id,
                "chunk_index": 0,
                "chunk_kind": "metadata",
                "metadata": {"chunk_kind": "metadata"},
            }
        ),
        _chunk(
            "# First Day Orientation\n"
            "09:00 - 09:30 Welcome breakfast and badge pickup.\n"
            "10:00 - 10:45 HR paperwork and benefits overview.\n"
            "11:00 - 11:45 Workstation setup with IT.",
            title="First Day Orientation",
            chunk_id="first-day-0",
        ).model_copy(update={"source_item_id": source_item_id, "chunk_index": 1}),
        _chunk(
            "# First Day Orientation\n"
            "12:00 - 13:00 Lunch with the team.\n"
            "13:00 - 14:00 Security and compliance briefing.\n"
            "14:00 - 15:00 Product and project overview.",
            title="First Day Orientation",
            chunk_id="first-day-1",
        ).model_copy(update={"source_item_id": source_item_id, "chunk_index": 2}),
        _chunk(
            "# First Day Orientation\n"
            "15:00 - 16:00 Meet your manager and confirm first-week goals.\n"
            "16:00 - 17:00 Pairing session with your onboarding buddy.\n"
            "18:00 - 18:15 End-of-day wrap-up and questions.",
            title="First Day Orientation",
            chunk_id="first-day-2",
        ).model_copy(update={"source_item_id": source_item_id, "chunk_index": 3}),
        _chunk(
            "# Quality Review\n"
            "- Owner confirmed.\n"
            "- Start-date dependency reviewed.\n"
            "- Employee-facing wording checked.",
            title="First Day Orientation",
            chunk_id="first-day-review",
        ).model_copy(update={"source_item_id": source_item_id, "chunk_index": 4}),
        _chunk(
            "# Export Metadata\n"
            "| Field | Value |\n"
            "| --- | --- |\n"
            "| Generated Date | 2026-06-02 |\n"
            "| Format | OneNote HTML |\n"
            "| Layout Style | agenda |",
            title="First Day Orientation",
            chunk_id="first-day-export",
        ).model_copy(update={"source_item_id": source_item_id, "chunk_index": 5}),
    ]

    response = asyncio.run(
        _answer_with_static_llm_for_chunks(
            "What should I expect on my first day of work?",
            chunks,
            (
                "On your first day, you have welcome breakfast at 09:00, HR paperwork at 10:00, "
                "and workstation setup at 11:00. [1]"
            ),
        )
    )

    assert response.answer.startswith("### First Day Orientation")
    assert "| Time | What happens |" in response.answer
    assert "09:00 - 09:30" in response.answer
    assert "18:00 - 18:15" in response.answer
    assert "End-of-day wrap-up and questions" in response.answer
    assert "Page:" not in response.answer
    assert "Owner:" not in response.answer
    assert "Summary:" not in response.answer
    assert "Owner confirmed" not in response.answer
    assert "Generated Date" not in response.answer
    assert "OneNote HTML" not in response.answer
    assert len(response.citations) == 3


def test_answer_service_repairs_dangling_markdown_table_pipes() -> None:
    import asyncio

    response = asyncio.run(
        _answer_with_static_llm(
            "What is the first day schedule?",
            _chunk(
                "# First Day Orientation\n"
                "09:00 - 09:30 Welcome breakfast.\n"
                "10:00 - 10:45 HR paperwork.\n"
                "11:00 - 11:45 Workstation setup.",
                title="First Day Orientation",
            ),
            (
                "### First Day Orientation\n\n"
                "| Time | Activity |\n"
                "| --- | --- |\n"
                "| 09:00 - 09:30 | Welcome breakfast.\n"
                "|\n"
                "| 10:00 - 10:45 | HR paperwork.\n"
                "|\n"
                "| 11:00 - 11:45 | Workstation setup. [1]\n"
                "|"
            ),
        )
    )

    assert "| 09:00 - 09:30 | Welcome breakfast. |" in response.answer
    assert "| 11:00 - 11:45 | Workstation setup. |" in response.answer
    assert "\n|\n" not in response.answer


def test_answer_service_answers_specific_overtime_question_from_matching_line() -> None:
    import asyncio

    response = asyncio.run(
        _answer_with_static_llm(
            "Is there any info about overtime?",
            _chunk(
                "# Working Hours\n"
                "Standard working hours: 09:00 - 18:00 (Monday-Friday)\n"
                "Flexible start: 08:00 - 10:00 (must complete 8 hours)\n"
                "Lunch break: 1 hour (unpaid)\n"
                "Overtime requires manager approval",
                title="Working Hours",
            ),
            (
                "### Working Hours\n\n"
                "- **Standard working hours:** 09:00 - 18:00 (Monday-Friday)\n"
                "- **Flexible start:** 08:00 - 10:00 (must complete 8 hours)\n"
                "- **Lunch break:** 1 hour (unpaid)"
            ),
        )
    )

    assert response.answer.startswith("### Working Hours")
    assert "- Overtime requires manager approval" in response.answer
    assert "09:00" not in response.answer
    assert "Flexible start" not in response.answer
    assert "Lunch break" not in response.answer
    assert "_Source:" not in response.answer


def test_answer_service_answers_from_internal_page_heading_body() -> None:
    import asyncio

    response = asyncio.run(
        _answer_with_static_llm(
            "what is the remote work policy",
            _chunk(
                "Page: Working Hours\n"
                "Standard working hours: 09:00 - 18:00 (Monday-Friday)\n"
                "Flexible start: 08:00 - 10:00 (must complete 8 hours)\n"
                "Lunch break: 1 hour (unpaid)\n"
                "Overtime requires manager approval\n\n"
                "Page: Paid Leave\n"
                "Annual leave: 20 days per year\n"
                "Sick leave: up to 10 days (medical note required after 3 days)\n"
                "Unpaid leave: requires HR approval\n\n"
                "Page: Remote Work Policy\n"
                "Allowed: up to 3 days per week\n"
                "Must be approved by manager\n"
                "Employees must be available on Slack during working hours",
                title="HR Policies",
            ),
            "HR Policies\nPage: Remote Work Policy [1]",
        )
    )

    assert response.answer.startswith("### Remote Work Policy")
    assert "- **Allowed:** up to 3 days per week" in response.answer
    assert "- Must be approved by manager" in response.answer
    assert "- Employees must be available on Slack during working hours" in response.answer
    assert "Paid Leave" not in response.answer
    assert "Working Hours" not in response.answer


def test_answer_service_rejects_stale_answer_from_same_mixed_chunk() -> None:
    import asyncio

    response = asyncio.run(
        _answer_with_static_llm(
            "What is the paid leave policy?",
            _chunk(
                "Page: Working Hours\n"
                "Standard working hours: 09:00 - 18:00 (Monday-Friday)\n\n"
                "Page: Paid Leave\n"
                "Annual leave: 20 days per year\n"
                "Sick leave: up to 10 days (medical note required after 3 days)\n"
                "Unpaid leave: requires HR approval\n\n"
                "Page: Remote Work Policy\n"
                "Allowed: up to 3 days per week\n"
                "Must be approved by manager",
                title="HR Policies",
            ),
            "### Remote Work Policy\n\n- **Allowed:** up to 3 days per week\n- Must be approved by manager [1]",
        )
    )

    assert response.answer.startswith("### Paid Leave")
    assert "- **Annual leave:** 20 days per year" in response.answer
    assert "- **Sick leave:** up to 10 days (medical note required after 3 days)" in response.answer
    assert "- **Unpaid leave:** requires HR approval" in response.answer
    assert "Remote Work Policy" not in response.answer


def test_answer_service_understands_home_office_question_without_exact_policy_words() -> None:
    import asyncio

    response = asyncio.run(
        _answer_with_static_llm(
            "Can I do my job from home?",
            _chunk(
                "# Remote Work Policy\n"
                "Allowed: up to 3 days per week\n"
                "Must be approved by manager\n"
                "Employees must be available on Slack during working hours",
                title="HR Policies",
            ),
            "No information",
            query_planner=StaticQueryPlanner(
                _planned_analysis(
                    "Can I do my job from home?",
                    semantic_queries=("remote work policy allowed manager approval",),
                    keyword_queries=("work from home",),
                    important_entities=("home", "remote work policy"),
                )
            ),
        )
    )

    assert response.answer.startswith("### Remote Work Policy")
    assert "- **Allowed:** up to 3 days per week" in response.answer
    assert "- Must be approved by manager" in response.answer
    assert "- Employees must be available on Slack during working hours" in response.answer
    assert response.citations


def test_answer_service_understands_start_time_question_without_working_hours_words() -> None:
    import asyncio

    response = asyncio.run(
        _answer_with_static_llm(
            "When can I begin my day?",
            _chunk(
                "# Working Hours\n"
                "Standard working hours: 09:00 - 18:00 (Monday-Friday)\n"
                "Flexible start: 08:00 - 10:00 (must complete 8 hours)\n"
                "Lunch break: 1 hour (unpaid)\n"
                "Overtime requires manager approval",
                title="HR Policies",
            ),
            "No information",
            query_planner=StaticQueryPlanner(
                _planned_analysis(
                    "When can I begin my day?",
                    semantic_queries=("standard working hours flexible start",),
                    keyword_queries=("begin day start time",),
                    important_entities=("begin", "day"),
                )
            ),
        )
    )

    assert response.answer.startswith("### Working Hours")
    assert "- **Standard working hours:** 09:00 - 18:00 (Monday-Friday)" in response.answer
    assert "- **Flexible start:** 08:00 - 10:00 (must complete 8 hours)" in response.answer
    assert "- **Lunch break:** 1 hour (unpaid)" in response.answer
    assert response.citations


def test_answer_service_uses_multiple_queries_for_thesis_focus_question() -> None:
    import asyncio
    from shared_schemas import AnswerRequest

    chunk = _chunk(
        "# Diploma Work\n"
        "The thesis focuses on building a OneNote RAG assistant for secure company knowledge retrieval.\n"
        "The project objective is to answer user questions using indexed notes and citations.",
        title="Diploma Work Overview",
    )
    retriever = QueryAwareRetriever(chunk)
    service = AnswerService(
        llm=StaticLlm("No information"),
        prompt_builder=PromptBuilder(),
        retriever=retriever,
        access_scope_resolver=AccessScopeResolver(),
        min_keyword_overlap=1,
        query_planner=StaticQueryPlanner(
            _planned_analysis(
                "What was the main focus of the thesis?",
                semantic_queries=("diploma work research focus project objective",),
                keyword_queries=("thesis main focus",),
                important_entities=("thesis", "main focus"),
            )
        ),
    )

    response = asyncio.run(
        service.answer(
            AnswerRequest(
                question="What was the main focus of the thesis?",
                user_context=UserContext(acl_tags=["employees"]),
                source_filters=["onenote"],
            )
        )
    )

    assert len(retriever.queries) > 1
    assert any("diploma work" in query for query in retriever.queries)
    assert response.answer.startswith("### Diploma Work Overview")
    assert "OneNote RAG assistant" in response.answer
    assert "_Source:" not in response.answer


def test_answer_service_allows_supported_cited_model_output() -> None:
    import asyncio

    response = asyncio.run(
        _answer_with_static_llm(
            "How do I configure Docker?",
            _chunk("Install Docker Desktop and configure Git credentials.", title="Developer setup"),
            "Install Docker Desktop and configure Git credentials. [1]",
        )
    )

    assert response.answer == (
        "### Developer setup\n\n"
        "Install Docker Desktop and configure Git credentials."
    )
    assert response.citations


def test_answer_service_appends_related_downloads_from_selected_context() -> None:
    import asyncio

    chunk = _chunk(
        "# Setup\n"
        "Step 2: download setup-installer.exe from the attached installer package.",
        title="Project setup",
    ).model_copy(
        update={
            "metadata": {
                "attachment_refs": [
                    {
                        "download_id": "download-1",
                        "file_name": "setup-installer.exe",
                        "file_extension": "exe",
                        "mime_type": "application/octet-stream",
                        "size_bytes": 12,
                        "readable": False,
                        "parent_source_item_id": "onenote:project-setup",
                        "parent_title": "Project setup",
                        "download_url": "/api/v1/attachments/download-1/download",
                    }
                ]
            }
        }
    )

    response = asyncio.run(
        _answer_with_static_llm(
            "How do I setup the project?",
            chunk,
            "Step 2 is to download setup-installer.exe from the installer package. [1]",
        )
    )

    assert response.downloads
    assert response.downloads[0].file_name == "setup-installer.exe"
    assert "### Downloads" in response.answer
    assert "[setup-installer.exe](/api/v1/attachments/download-1/download)" in response.answer


def test_answer_service_lists_all_downloads_from_cited_page() -> None:
    import asyncio
    from shared_schemas import AnswerRequest

    chunk = _chunk(
        "# Setup\n"
        "Install Docker Desktop and configure Git credentials.",
        title="Project setup",
        chunk_id="project-setup",
    )
    service = AnswerService(
        llm=StaticLlm("Install Docker Desktop and configure Git credentials. [1]"),
        prompt_builder=PromptBuilder(),
        retriever=StaticRetriever([chunk]),
        metadata=StaticMetadata(
            [],
            attachments=[
                _attachment(
                    "setup-installer.exe",
                    parent_source_item_id=chunk.source_item_id,
                    parent_title=chunk.title,
                    download_id="installer",
                ),
                _attachment(
                    "setup-tools.zip",
                    parent_source_item_id=chunk.source_item_id,
                    parent_title=chunk.title,
                    download_id="tools",
                ),
            ],
        ),
        access_scope_resolver=AccessScopeResolver(),
        min_keyword_overlap=1,
    )

    response = asyncio.run(
        service.answer(
            AnswerRequest(
                question="How do I configure Docker?",
                user_context=UserContext(acl_tags=["employees"]),
                source_filters=["onenote"],
            )
        )
    )

    assert [download.file_name for download in response.downloads] == [
        "setup-installer.exe",
        "setup-tools.zip",
    ]
    assert "[setup-installer.exe](/api/v1/attachments/installer/download)" in response.answer
    assert "[setup-tools.zip](/api/v1/attachments/tools/download)" in response.answer


def test_answer_service_combines_page_body_and_readable_attachment_evidence() -> None:
    import asyncio

    page = _chunk(
        "# abc\nFact A: the release owner is Platform Enablement.",
        title="abc",
        chunk_id="page-abc",
    ).model_copy(update={"source_item_id": "onenote:page-abc", "source_url": "https://example.test/page-abc"})
    attachment = _readable_attachment_chunk(
        "# file.docx\nChecklist requirement: QA sign-off must be completed before rollout.",
        parent_source_item_id="onenote:page-abc",
        parent_title="abc",
        file_name="file.docx",
    )

    response = asyncio.run(
        _answer_with_static_llm_for_chunks(
            "For abc, who owns the release and what does the attached checklist require?",
            [page, attachment],
            (
                "### abc\n\n"
                "The release owner is Platform Enablement, and the attached checklist requires QA sign-off before rollout. [1] [2]"
            ),
        )
    )

    assert response.answer.startswith("### abc")
    assert "Platform Enablement" in response.answer
    assert "QA sign-off" in response.answer
    assert [citation.source_item_id for citation in response.citations] == [
        "onenote:page-abc",
        "onenote-attachment:file.docx",
    ]
    assert response.citations[1].title == "Page: abc | File: file.docx"
    assert response.citations[1].metadata["citation_page_title"] == "abc"
    assert response.citations[1].metadata["citation_file_name"] == "file.docx"


def test_focused_parent_page_keeps_readable_attachment_chunks_eligible() -> None:
    import asyncio
    from shared_schemas import AnswerRequest

    attachment = _readable_attachment_chunk(
        "# file.docx\nChecklist requirement: QA sign-off must be completed before rollout.",
        parent_source_item_id="onenote:page-abc",
        parent_title="abc",
        file_name="file.docx",
    )
    service = AnswerService(
        llm=StaticLlm("The attached file says QA sign-off must be completed before rollout. [1]"),
        prompt_builder=PromptBuilder(),
        retriever=StaticRetriever([attachment]),
        access_scope_resolver=AccessScopeResolver(),
        min_keyword_overlap=1,
    )

    response = asyncio.run(
        service.answer(
            AnswerRequest(
                question="What does abc's attached checklist require?",
                user_context=UserContext(acl_tags=["employees"]),
                source_filters=["onenote"],
                focus_source_item_ids=["onenote:page-abc"],
            )
        )
    )

    assert response.answer != NO_INFORMATION_ANSWER
    assert response.citations
    assert response.citations[0].source_item_id == "onenote-attachment:file.docx"
    assert response.citations[0].title == "Page: abc | File: file.docx"
