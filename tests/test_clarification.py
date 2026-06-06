"""Tests for quiz-style clarification of ambiguous questions.

When a specific question is equally well answered by several distinct pages, the
assistant asks the user which one they mean instead of guessing. Picking a page
(via ``focus_source_item_ids``) then answers from that page only.
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


def _chunk(title: str, text: str, source_item_id: str, *, score: float = 6.0) -> ChunkDocument:
    return ChunkDocument(
        tenant_id="default",
        source_system="onenote",
        source_container="container",
        source_item_id=source_item_id,
        source_url=f"https://example.test/{source_item_id}",
        title=title,
        section_path=None,
        last_modified_utc=datetime(2026, 5, 1, tzinfo=UTC),
        acl_tags=["employees"],
        acl_bindings=[],
        content_hash=source_item_id,
        chunk_id=f"{source_item_id}-0",
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

    def __init__(self, chunks):
        self.chunks = chunks

    async def retrieve(self, request):
        scope = request.access_scope or AccessScope(
            user_id="u",
            email="e@example.test",
            tenant_id=request.user_context.tenant_id,
            allowed_acl_tags=request.user_context.acl_tags,
        )
        chunks = [chunk.model_copy() for chunk in self.chunks]
        if request.focus_source_item_ids:
            focus = set(request.focus_source_item_ids)
            chunks = [chunk for chunk in chunks if chunk.source_item_id in focus]
        return RetrievalResult(
            chunks=chunks,
            metadata=RetrievalMetadata(
                strategy="static",
                access_scope=scope,
                requested_top_k=request.top_k,
                candidate_count=len(chunks),
                returned_count=len(chunks),
                filtered_count=0,
            ),
        )

    async def ready(self) -> bool:
        return True


class _DefersLlm:
    provider_name = "test"
    model_name = "test"

    async def generate(self, prompt) -> GenerationResult:
        # Echo the first context block so a focused answer is non-empty.
        text = "\n".join(prompt.context_blocks) or "No information"
        return GenerationResult(provider="test", model="test", answer_text=text)

    async def ready(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return [self.model_name]


# Two distinct pages that both directly answer a password-reset question.
_VPN = _chunk(
    "VPN Password Reset",
    "# VPN Password Reset\nTo reset your VPN password, open the VPN portal, click Reset Password, and sign in again.",
    "page-vpn",
)
_EMAIL = _chunk(
    "Email Password Reset",
    "# Email Password Reset\nTo reset your email password, open webmail settings, click Reset Password, and confirm.",
    "page-email",
)
_PARKING = _chunk(
    "Office Parking",
    "# Office Parking\nThe garage opens at 7am. Badge in at the gate to enter.",
    "page-parking",
)


def _service(chunks, **kwargs):
    return AnswerService(
        llm=_DefersLlm(),
        prompt_builder=PromptBuilder(),
        retriever=_StaticRetriever(chunks),
        access_scope_resolver=AccessScopeResolver(),
        reranker=None,
        min_keyword_overlap=1,
        **kwargs,
    )


def _answer(question, chunks, *, focus=None, **kwargs):
    service = _service(chunks, **kwargs)
    request = AnswerRequest(
        question=question,
        user_context=UserContext(acl_tags=["employees"]),
        top_k=8,
        focus_source_item_ids=focus or [],
    )
    return asyncio.run(service.answer(request))


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #
def test_two_equally_strong_pages_trigger_clarification() -> None:
    response = _answer("how do I reset my password", [_VPN, _EMAIL])
    assert response.clarification is not None
    titles = {option.title for option in response.clarification.options}
    assert titles == {"VPN Password Reset", "Email Password Reset"}
    assert response.citations == []
    assert "which" in response.answer.lower()
    assert response.clarification.original_question == "how do I reset my password"
    assert response.retrieval_meta.evidence_sufficiency == "AMBIGUOUS_MULTIPLE_TOPICS"


def test_option_count_is_dynamic_not_fixed() -> None:
    # Only two candidates exist -> exactly two options (not padded to a fixed 3).
    response = _answer("how do I reset my password", [_VPN, _EMAIL, _PARKING])
    assert response.clarification is not None
    assert len(response.clarification.options) == 2


def test_single_relevant_page_answers_without_clarification() -> None:
    response = _answer("how do I reset my password", [_VPN, _PARKING])
    assert response.clarification is None
    assert response.answer != ""
    assert "VPN" in response.answer or response.citations


def test_clarification_can_be_disabled() -> None:
    response = _answer("how do I reset my password", [_VPN, _EMAIL], clarify_enabled=False)
    assert response.clarification is None


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #
def test_focus_selection_answers_from_chosen_page_only() -> None:
    response = _answer("how do I reset my password", [_VPN, _EMAIL], focus=["page-email"])
    assert response.clarification is None
    assert "email" in response.answer.lower()
    assert "vpn" not in response.answer.lower()


def test_focus_selection_never_re_clarifies() -> None:
    response = _answer("how do I reset my password", [_VPN, _EMAIL], focus=["page-vpn"])
    assert response.clarification is None
