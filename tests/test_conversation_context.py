"""Tests for conversational follow-up context (per-session memory).

A follow-up question that omits the subject ("how do I run it?") must be
resolved against earlier turns so retrieval targets the right project instead
of an unrelated one. OneNote-only.
"""

from __future__ import annotations

import asyncio

from shared_schemas import (
    AccessScope,
    AnswerRequest,
    AppSettings,
    ConversationTurn,
    RetrievalMetadata,
    RetrievalResult,
    UserContext,
)

from rag_api.ports import GenerationResult
from rag_api.services import AccessScopeResolver, AnswerService, PromptBuilder
from rag_api.services.conversation_context import carried_subject, contextualize_question, is_followup_question
from sync_worker.ingestion import TextChunker

from fixtures.onenote_flutter_hmi import flutter_hmi_document

NO_INFORMATION_ANSWER = "I could not find that information in the available OneNote notes or readable attachments."

RENDERER_TEXT = """# Renderer Engine Setup

Section: Projects Setup
Repository: renderer-engine

## Overview

The renderer engine is a C++ rasterizer for embedded dashboards.

## Install

```bash
git clone https://github.com/company/renderer-engine.git
cd renderer-engine
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
```

## Run

```bash
cmake --build build --config Debug
./build/renderer_engine --scene demo.scene
```

## Verification

- The renderer engine window opens and renders the demo scene.
- Frame timing stays under sixteen milliseconds.
"""


def _renderer_document():
    document = flutter_hmi_document().model_copy(
        update={
            "source_item_id": "onenote:renderer-engine",
            "title": "Renderer Engine Setup",
            "section_path": "Projects Setup / Renderer Engine Setup",
            "content_text": RENDERER_TEXT,
            "content_hash": "renderer-hash",
        }
    )
    return document


class StaticRetriever:
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
        return RetrievalResult(
            chunks=self.chunks,
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


class NoInfoLlm:
    provider_name = "test"
    model_name = "test"

    async def generate(self, prompt):
        return GenerationResult(provider="test", model="test", answer_text=NO_INFORMATION_ANSWER)

    async def ready(self) -> bool:
        return True

    async def list_models(self):
        return [self.model_name]


def _answer(request: AnswerRequest) -> str:
    chunker = TextChunker(AppSettings())
    chunks = chunker.chunk(flutter_hmi_document()) + chunker.chunk(_renderer_document())
    service = AnswerService(
        llm=NoInfoLlm(),
        prompt_builder=PromptBuilder(),
        retriever=StaticRetriever(chunks),
        access_scope_resolver=AccessScopeResolver(),
        reranker=None,
        min_keyword_overlap=1,
    )
    return asyncio.run(service.answer(request)).answer


# --------------------------------------------------------------------------- #
# Unit
# --------------------------------------------------------------------------- #
def test_followup_detection() -> None:
    assert is_followup_question("how do I run it")
    assert is_followup_question("what about deployment")
    assert is_followup_question("and the configuration")
    assert not is_followup_question("how do I set up the flutter embedded hmi")


def test_carried_subject_uses_latest_user_subject() -> None:
    history = [
        ConversationTurn(role="user", content="tell me about the flutter embedded hmi setup"),
        ConversationTurn(role="assistant", content="..."),
        ConversationTurn(role="user", content="how do I configure the renderer engine project"),
        ConversationTurn(role="assistant", content="..."),
    ]
    assert "renderer engine" in carried_subject(history).lower()


def test_contextualize_only_rewrites_followups() -> None:
    history = [ConversationTurn(role="user", content="how do I set up the renderer engine project")]
    assert "renderer engine" in contextualize_question("how do I run it", history).lower()
    # A self-contained question that names a different subject is left alone.
    standalone = "how do I set up the flutter embedded hmi"
    assert contextualize_question(standalone, history) == standalone
    # No history -> unchanged.
    assert contextualize_question("how do I run it", []) == "how do I run it"


# --------------------------------------------------------------------------- #
# End-to-end: follow-up retrieves the right project
# --------------------------------------------------------------------------- #
def test_followup_without_subject_targets_prior_project() -> None:
    history = [
        ConversationTurn(role="user", content="how do I set up the renderer engine project"),
        ConversationTurn(role="assistant", content="Clone the repo and build it with cmake."),
    ]
    answer = _answer(
        AnswerRequest(
            question="how do I run it",
            history=history,
            user_context=UserContext(acl_tags=["employees"]),
            top_k=8,
        )
    )
    assert "renderer" in answer.lower()
    # It must NOT drift to the unrelated Flutter project.
    assert "flutter pub get" not in answer
    assert "WAYLAND_DISPLAY" not in answer


def test_followup_without_history_is_ambiguous_not_crashing() -> None:
    # Same bare question with no history should still answer (no exception).
    answer = _answer(
        AnswerRequest(
            question="how do I run the renderer engine",
            history=[],
            user_context=UserContext(acl_tags=["employees"]),
            top_k=8,
        )
    )
    assert "renderer" in answer.lower()
