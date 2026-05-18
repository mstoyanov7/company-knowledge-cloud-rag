from __future__ import annotations

from datetime import UTC, datetime

from rag_api.adapters.llm.mock import MockLlmAdapter
from rag_api.services import AccessScopeResolver, AnswerService, PromptBuilder
from shared_schemas import (
    AccessScope,
    AppSettings,
    ChunkDocument,
    RetrievalMetadata,
    RetrievalRequest,
    RetrievalResult,
    UserContext,
)


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


async def _answer_with_static_llm(question: str, chunk: ChunkDocument, answer_text: str):
    return await _answer_with_static_llm_for_chunks(question, [chunk], answer_text)


async def _answer_with_static_llm_for_chunks(question: str, chunks: list[ChunkDocument], answer_text: str):
    service = AnswerService(
        llm=StaticLlm(answer_text),
        prompt_builder=PromptBuilder(),
        retriever=StaticRetriever(chunks),
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


def test_answer_service_returns_no_information_for_irrelevant_retrieval_hit() -> None:
    import asyncio

    response = asyncio.run(
        _answer_for(
            "What is the company vacation policy?",
            _chunk("Install Docker Desktop and configure Git credentials.", title="Developer setup"),
        )
    )

    assert response.answer == "No information"
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

    assert response.answer != "No information"
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

    assert response.answer == "### Developer setup\n\n- Install Docker Desktop and configure Git credentials [1]"
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
        "then sign in and configure Git credentials. [1]"
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

    assert response.answer == "### Developer setup\n\n- Install Docker Desktop and configure Git credentials [1]"
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

    assert response.answer == "### Developer setup\n\n- Install Docker Desktop and configure Git credentials [1]"
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
        "- Run the Docker Desktop installer from the onboarding package [1]\n"
        "- After installation, sign in and configure Git credentials [1]"
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
    assert "- **Standard working hours:** 09:00 - 18:00 (Monday-Friday) [1]" in response.answer
    assert "- **Flexible start:** 08:00 - 10:00 (must complete 8 hours) [1]" in response.answer
    assert "- **Lunch break:** 1 hour (unpaid) [1]" in response.answer
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

    assert response.answer == "No information"
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
    assert "- **Standard working hours:** 09:00 - 18:00 (Monday-Friday) [1]" in response.answer
    assert "- **Flexible start:** 08:00 - 10:00 (must complete 8 hours) [1]" in response.answer
    assert "- **Lunch break:** 1 hour (unpaid) [1]" in response.answer


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
    assert "- **Allowed:** up to 3 days per week [1]" in response.answer
    assert "- Must be approved by manager [1]" in response.answer
    assert "- Employees must be available on Slack during working hours [1]" in response.answer
    assert "Paid Leave" not in response.answer
    assert "Working Hours" not in response.answer


def test_answer_service_allows_supported_cited_model_output() -> None:
    import asyncio

    response = asyncio.run(
        _answer_with_static_llm(
            "How do I configure Docker?",
            _chunk("Install Docker Desktop and configure Git credentials.", title="Developer setup"),
            "Install Docker Desktop and configure Git credentials. [1]",
        )
    )

    assert response.answer == "### Developer setup\n\nInstall Docker Desktop and configure Git credentials. [1]"
    assert response.citations
