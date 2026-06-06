from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from rag_api.ports import GenerationResult
from rag_api.services import AccessScopeResolver, AnswerService, PromptBuilder, QueryPlanner
from rag_api.services.evidence_grading import PARTIAL_ANSWER_FOUND
from rag_api.services.query_understanding import analyze_question
from rag_api.services.retrieval_ranking import analysis_relevance_score
from shared_schemas import (
    AccessScope,
    AnswerRequest,
    ChunkDocument,
    RetrievalMetadata,
    RetrievalRequest,
    RetrievalResult,
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


class PlanningGradingLlm:
    provider_name = "test"
    model_name = "test"

    async def generate(self, prompt):
        return GenerationResult(
            provider=self.provider_name,
            model=self.model_name,
            answer_text=NO_INFORMATION_ANSWER,
        )

    async def ready(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return [self.model_name]

    async def plan_queries(self, **kwargs):
        question = kwargs["question"].lower()
        if any(term in question for term in ("leave", "vacation", "annual", "отпуск")):
            return _leave_plan(kwargs["question"])
        if any(term in question for term in ("salary", "payment", "paid", "payroll", "заплат", "плащан")):
            return _salary_plan(kwargs["question"])
        return {}

    async def grade_relevance(self, *, question: str, question_analysis: dict[str, object], chunks: list[dict[str, object]]):
        must = {str(value).lower() for value in question_analysis.get("must_have_concepts", [])}
        grades = []
        for chunk in chunks:
            title = str(chunk["title"]).lower()
            content = str(chunk["content"]).lower()
            haystack = f"{title} {content}"
            if {"salary", "payment"}.intersection(must) or {"заплата", "плащане"}.intersection(must):
                if "salary payment" in title or "плащане на заплата" in title:
                    relevance = "direct" if "25" in content else "partial"
                    grades.append(_grade(chunk["chunk_id"], relevance, relevance != "related"))
                    continue
            if {"leave", "annual", "vacation"}.intersection(must) or "отпуск" in must:
                if "paid leave" in title or "платен отпуск" in title:
                    grades.append(_grade(chunk["chunk_id"], "direct", True))
                    continue
            grades.append(_grade(chunk["chunk_id"], "related" if "paid" in haystack or "плат" in haystack else "irrelevant", False))
        return {"chunks": grades}


def _grade(chunk_id: str, relevance: str, answers_question: bool) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "relevance": relevance,
        "answers_question": answers_question,
        "reason": relevance,
        "confidence": 0.9 if answers_question else 0.4,
    }


def _salary_plan(question: str) -> dict[str, object]:
    return {
        "original_question": question,
        "rewritten_question": "salary payment date",
        "answer_type": "date_or_time",
        "key_entities": ["salary payment", "salary", "payment", "payroll", "заплата", "плащане"],
        "key_phrases": ["salary payment", "salary paid", "receive salary payment", "плащане на заплата"],
        "semantic_queries": [
            "salary payment date",
            "when salary is paid",
            "payroll salary payment",
            "receive salary payment",
            "дата плащане заплата",
        ],
        "keyword_queries": ["salary paid", "salary payment", "payroll"],
        "must_have_concepts": ["salary", "payment", "заплата", "плащане"],
        "avoid_concepts": ["leave", "vacation", "отпуск"],
        "expected_evidence_type": "date_or_time_value",
    }


def _leave_plan(question: str) -> dict[str, object]:
    return {
        "original_question": question,
        "rewritten_question": "paid leave allowance days",
        "answer_type": "specific_fact",
        "key_entities": ["paid leave", "annual leave", "vacation days", "отпуск"],
        "key_phrases": ["paid leave", "annual leave", "vacation days", "платен отпуск"],
        "semantic_queries": [
            "paid leave days",
            "annual leave allowance",
            "vacation days entitlement",
            "days of paid annual leave",
        ],
        "keyword_queries": ["paid leave days", "annual leave", "vacation days"],
        "must_have_concepts": ["leave", "annual", "vacation", "отпуск"],
        "avoid_concepts": ["salary", "payment", "payroll", "заплата"],
        "expected_evidence_type": "specific_value_or_limit",
    }


def _chunk(title: str, text: str, *, chunk_id: str | None = None, language: str = "en") -> ChunkDocument:
    return ChunkDocument(
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="onenote",
        source_item_id=f"onenote:{chunk_id or title}",
        source_url="https://example.test",
        title=title,
        section_path="HR",
        last_modified_utc=datetime(2026, 4, 26, tzinfo=UTC),
        acl_tags=["employees"],
        content_hash=f"hash:{chunk_id or title}",
        chunk_id=chunk_id or title,
        chunk_index=0,
        chunk_text=text,
        embedding_model="token-hash-v1",
        language=language,
    )


def _salary_chunk(text: str | None = None, *, title: str = "Salary Payment", language: str = "en") -> ChunkDocument:
    return _chunk(
        title,
        text or "# Salary Payment\nPaid monthly on the 25th\nBank transfer only",
        chunk_id="salary-payment",
        language=language,
    )


def _leave_chunk() -> ChunkDocument:
    return _chunk(
        "Paid leave",
        "# Paid Leave\nAnnual leave: 20 days per year\nSick leave: up to 10 days\nUnpaid leave requires HR approval",
        chunk_id="paid-leave",
    )


async def _answer(question: str, chunks: list[ChunkDocument]):
    llm = PlanningGradingLlm()
    service = AnswerService(
        llm=llm,
        prompt_builder=PromptBuilder(),
        retriever=StaticRetriever(chunks),
        access_scope_resolver=AccessScopeResolver(),
        min_keyword_overlap=1,
        query_planner=QueryPlanner(llm=llm),
    )
    return await service.answer(
        AnswerRequest(
            question=question,
            user_context=UserContext(acl_tags=["employees"]),
            source_filters=["onenote"],
            top_k=3,
        )
    )


def test_phrase_aware_reranking_prefers_salary_payment_over_paid_leave() -> None:
    analysis = analyze_question("When is the salary paid?")
    analysis = QueryPlanner(llm=PlanningGradingLlm())
    planned = asyncio.run(analysis.plan("When is the salary paid?"))

    salary_score = analysis_relevance_score(planned, _salary_chunk())
    leave_score = analysis_relevance_score(planned, _leave_chunk())

    assert salary_score > leave_score


def test_salary_payment_paraphrases_resolve_to_salary_payment_source() -> None:
    questions = [
        "When is the salary paid?",
        "On what date will I receive my payment?",
        "What day do we get paid?",
        "When is payroll?",
        "When do employees receive their salary?",
    ]

    for question in questions:
        response = asyncio.run(_answer(question, [_leave_chunk(), _salary_chunk()]))

        assert response.answer != NO_INFORMATION_ANSWER
        assert response.citations
        assert response.citations[0].title == "Salary Payment"
        assert "25th" in response.answer
        assert "Paid leave" not in response.answer


def test_paid_leave_paraphrases_resolve_to_paid_leave_source() -> None:
    questions = [
        "How many paid leave days do I have?",
        "How much annual leave is allowed?",
        "How many vacation days are there?",
    ]

    for question in questions:
        response = asyncio.run(_answer(question, [_salary_chunk(), _leave_chunk()]))

        assert response.answer != NO_INFORMATION_ANSWER
        assert response.citations
        assert response.citations[0].title == "Paid leave"
        assert "20 days" in response.answer
        assert "Salary Payment" not in response.answer


def test_keyword_overlap_wrong_topic_is_not_enough() -> None:
    response = asyncio.run(_answer("When is the salary paid?", [_leave_chunk()]))

    assert response.answer == NO_INFORMATION_ANSWER
    assert response.citations == []
    assert response.retrieval_meta.evidence_sufficiency in {"RELATED_BUT_NOT_ENOUGH", "NO_RELEVANT_INFORMATION"}


def test_partial_evidence_is_marked_partial_and_kept_with_source() -> None:
    response = asyncio.run(
        _answer(
            "When is the salary paid?",
            [_salary_chunk("# Salary Payment\nPaid monthly\nBank transfer only")],
        )
    )

    assert response.retrieval_meta.evidence_sufficiency == PARTIAL_ANSWER_FOUND
    assert response.citations[0].title == "Salary Payment"
    assert "Paid monthly" in response.answer


def test_citations_only_use_direct_salary_source() -> None:
    response = asyncio.run(_answer("When is the salary paid?", [_leave_chunk(), _salary_chunk()]))

    assert [citation.title for citation in response.citations] == ["Salary Payment"]
    assert "_Source:" not in response.answer


def test_bulgarian_paraphrase_retrieves_bulgarian_salary_note() -> None:
    response = asyncio.run(
        _answer(
            "Кога се изплаща заплатата?",
            [
                _chunk("Платен отпуск", "# Платен отпуск\nГодишен отпуск: 20 дни", chunk_id="bg-leave", language="bg"),
                _salary_chunk(
                    "# Плащане на заплата\nЗаплатата се изплаща месечно на 25-то число\nСамо банков превод",
                    title="Плащане на заплата",
                    language="bg",
                ),
            ],
        )
    )

    assert response.citations[0].title == "Плащане на заплата"
    assert "25-то" in response.answer


def test_english_question_can_retrieve_bulgarian_note_content() -> None:
    response = asyncio.run(
        _answer(
            "When is the salary paid?",
            [
                _salary_chunk(
                    "# Плащане на заплата\nЗаплатата се изплаща месечно на 25-то число\nСамо банков превод",
                    title="Плащане на заплата",
                    language="bg",
                )
            ],
        )
    )

    assert response.citations[0].title == "Плащане на заплата"
    assert "25-то" in response.answer


def test_bulgarian_question_can_retrieve_english_note_content() -> None:
    response = asyncio.run(_answer("Кога се изплаща заплатата?", [_salary_chunk()]))

    assert response.citations[0].title == "Salary Payment"
    assert "25th" in response.answer
