"""Tests for the "partially related" hedge tier.

The assistant should only reply with the bare "no information" message when there
is genuinely nothing relevant. When retrieval found something topically related
but not confident enough to be a direct answer, it should surface that content
behind a friendly caveat instead of dead-ending. Wrong-topic and unrelated hits
must still be rejected so the hedge never produces a misleading near-answer.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from shared_schemas import (
    AccessScope,
    AnswerRequest,
    ChunkDocument,
    RetrievalMetadata,
    RetrievalResult,
    UserContext,
)

from rag_api.ports import GenerationResult
from rag_api.services import AccessScopeResolver, AnswerService, PromptBuilder
from rag_api.services.answer_service import (
    HEDGED_ANSWER_PREAMBLE,
    NO_INFORMATION_ANSWER,
    _chunk_supports_hedge,
    _related_chunks_for_hedge,
)
from rag_api.services.evidence_grading import EvidenceGrade
from rag_api.services.query_understanding import analyze_question


def _chunk(title: str, text: str, chunk_id: str, *, score: float = 0.0) -> ChunkDocument:
    return ChunkDocument(
        tenant_id="default",
        source_system="onenote",
        source_container="container",
        source_item_id=chunk_id,
        source_url="https://example.test/page",
        title=title,
        section_path=None,
        last_modified_utc=datetime(2026, 5, 1, tzinfo=UTC),
        acl_tags=["employees"],
        acl_bindings=[],
        content_hash=chunk_id,
        chunk_id=chunk_id,
        chunk_index=0,
        chunk_text=text,
        embedding_model="token-hash-v1",
        language="en",
        tags=[],
        metadata={},
        score=score,
    )


class _StaticRetriever:
    name = "static"

    def __init__(self, chunks: list[ChunkDocument]) -> None:
        self.chunks = chunks

    async def retrieve(self, request: AnswerRequest) -> RetrievalResult:
        scope = request.access_scope or AccessScope(
            user_id="u",
            email="e@example.test",
            tenant_id=request.user_context.tenant_id,
            allowed_acl_tags=request.user_context.acl_tags,
        )
        return RetrievalResult(
            chunks=[chunk.model_copy() for chunk in self.chunks],
            metadata=RetrievalMetadata(
                strategy="static",
                access_scope=scope,
                requested_top_k=request.top_k,
                candidate_count=len(self.chunks),
                returned_count=len(self.chunks),
                filtered_count=0,
            ),
        )

    async def ready(self) -> bool:
        return True


class _CautiousLlm:
    """Defers on generation and grades every chunk only 'related' - the typical
    behaviour of a small local model that is unsure."""

    provider_name = "test"
    model_name = "test"

    async def generate(self, prompt) -> GenerationResult:
        return GenerationResult(provider="test", model="test", answer_text=NO_INFORMATION_ANSWER)

    async def grade_relevance(self, *, question, question_analysis, chunks):
        return {
            "chunks": [
                {
                    "chunk_id": chunk["chunk_id"],
                    "relevance": "related",
                    "answers_question": False,
                    "reason": "shares topic",
                    "confidence": 0.5,
                }
                for chunk in chunks
            ]
        }

    async def ready(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return [self.model_name]


def _answer(question: str, chunks: list[ChunkDocument], *, llm=None):
    service = AnswerService(
        llm=llm or _CautiousLlm(),
        prompt_builder=PromptBuilder(),
        retriever=_StaticRetriever(chunks),
        access_scope_resolver=AccessScopeResolver(),
        reranker=None,
        min_keyword_overlap=1,
    )
    request = AnswerRequest(question=question, user_context=UserContext(acl_tags=["employees"]), top_k=8)
    return asyncio.run(service.answer(request))


# --------------------------------------------------------------------------- #
# End-to-end behaviour
# --------------------------------------------------------------------------- #
def test_related_but_not_confident_returns_friendly_hedge() -> None:
    chunk = _chunk(
        "Engineering Mentorship",
        "Our engineering mentorship connects new engineers with experienced staff for career growth. "
        "Sessions are informal and ongoing.",
        "mentorship",
    )
    response = _answer("what is the mentorship program enrollment deadline", [chunk])

    assert response.answer.startswith(HEDGED_ANSWER_PREAMBLE)
    assert "mentorship" in response.answer.lower()
    assert response.answer != NO_INFORMATION_ANSWER
    assert [citation.title for citation in response.citations] == ["Engineering Mentorship"]
    assert response.retrieval_meta.evidence_sufficiency == "RELATED_BUT_NOT_ENOUGH"


def test_wrong_topic_overlap_still_returns_no_information() -> None:
    # "salary paid" vs a paid-leave note shares only the weak word "paid"; that
    # is not a real topical link, so no misleading hedge should be produced.
    leave = _chunk(
        "Paid leave",
        "# Paid Leave\nAnnual leave: 20 days per year\nSick leave: up to 10 days",
        "leave",
    )
    response = _answer("when is the salary paid", [leave])

    assert response.answer == NO_INFORMATION_ANSWER
    assert response.citations == []


def test_unrelated_hit_returns_no_information() -> None:
    vpn = _chunk("VPN Setup", "# VPN Setup\nInstall the client and sign in with SSO.", "vpn")
    response = _answer("what is the office snack budget for marketing", [vpn])

    assert response.answer == NO_INFORMATION_ANSWER
    assert response.citations == []


def test_hedge_never_produces_empty_caveat_without_content() -> None:
    # A title-only chunk has no extractable body; the hedge must decline rather
    # than emit the caveat with nothing useful after it.
    title_only = _chunk("Mentorship Program", "Mentorship Program", "title-only")
    response = _answer("what is the mentorship program enrollment deadline", [title_only])

    assert response.answer == NO_INFORMATION_ANSWER or response.answer.startswith(HEDGED_ANSWER_PREAMBLE)
    if response.answer.startswith(HEDGED_ANSWER_PREAMBLE):
        # If it does hedge, there must be real content after the caveat.
        body = response.answer[len(HEDGED_ANSWER_PREAMBLE):].strip()
        assert len(body) > 0
        assert response.citations


# --------------------------------------------------------------------------- #
# Hedge gating unit tests (precision guards)
# --------------------------------------------------------------------------- #
def test_chunk_supports_hedge_accepts_meaningful_concept() -> None:
    analysis = analyze_question("what is the mentorship program enrollment deadline")
    chunk = _chunk("Engineering Mentorship", "The mentorship pairs engineers with mentors.", "m")
    assert _chunk_supports_hedge(analysis, chunk) is True


def test_chunk_supports_hedge_rejects_single_weak_shared_word() -> None:
    analysis = analyze_question("when is the salary paid")
    leave = _chunk("Paid leave", "Annual paid leave is 20 days.", "leave")
    assert _chunk_supports_hedge(analysis, leave) is False


def test_chunk_supports_hedge_rejects_no_overlap() -> None:
    analysis = analyze_question("what is the parental leave policy")
    chunk = _chunk("VPN Setup", "Install the client and sign in with SSO.", "vpn")
    assert _chunk_supports_hedge(analysis, chunk) is False


def test_related_chunks_for_hedge_drops_irrelevant_grades() -> None:
    analysis = analyze_question("what is the mentorship program enrollment deadline")
    related = _chunk("Engineering Mentorship", "The mentorship pairs engineers with mentors.", "m")
    junk = _chunk("Cafeteria Menu", "Today we serve pasta and salad.", "c")
    grades = (
        EvidenceGrade("m", "related", False, "shares topic", 0.5),
        EvidenceGrade("c", "irrelevant", False, "off topic", 0.2),
    )
    picked = _related_chunks_for_hedge(analysis, grades, [related, junk])
    assert [chunk.chunk_id for chunk in picked] == ["m"]
