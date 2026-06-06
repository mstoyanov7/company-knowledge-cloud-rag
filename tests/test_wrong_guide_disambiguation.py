"""Regression tests: a partial query must reach the *right* setup guide.

Asking "how to setup flutter project" used to answer from "Internal DevTools CLI
Setup" because both pages share the generic scaffolding words "setup"/"project".
A confident answer now requires the question's distinctive subject ("flutter"),
so the correct page wins when present and the wrong guide is never answered
confidently when the right one is missing.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from shared_schemas import (
    AccessScope,
    AnswerRequest,
    AppSettings,
    RetrievalMetadata,
    RetrievalResult,
    SourceDocument,
    UserContext,
)

from rag_api.ports import GenerationResult
from rag_api.services import AccessScopeResolver, AnswerService, PromptBuilder
from rag_api.services.answer_service import HEDGED_ANSWER_PREAMBLE, NO_INFORMATION_ANSWER
from rag_api.services.query_understanding import analyze_question
from rag_api.services.retrieval_ranking import rank_chunks_by_question_analysis
from sync_worker.ingestion import TextChunker

from fixtures.onenote_flutter_hmi import flutter_hmi_document

FLUTTER_QUERY = "how to setup flutter project"

_DEVTOOLS_TEXT = """# Internal DevTools CLI Setup

Projects Setup - 01 Internal DevTools CLI Setup

Section: Projects Setup

Summary: Setup guide for the internal DevTools command line interface used to scaffold and run company projects.

## Overview
The Internal DevTools CLI helps engineers create, configure, and run new projects.

## Install
```bash
npm install -g @company/devtools-cli
devtools login
```

## Configuration
```bash
devtools init --project my-app
devtools config set registry https://registry.company.test
```

## Run
```bash
devtools run --project my-app
```

## Verification
Run `devtools doctor` to verify the project setup.
"""

_MODELVIEWER_TEXT = """# ModelViewer Setup

Projects Setup - ModelViewer Setup

## Overview
ModelViewer renders 3D meshes in the browser for design review.

## Install
Install the viewer package and run `modelviewer serve`.
"""

_MODELRUNNER_TEXT = """# ModelRunner Setup

Projects Setup - ModelRunner Setup

## Overview
ModelRunner executes simulation batches for model validation.

## Install
Install the runner package and run `modelrunner start`.
"""

_MODELVIEWR_TEXT = """# ModelViewr Setup

Projects Setup - ModelViewr Setup

## Overview
ModelViewr is a separate internal preview utility.

## Install
Install the preview utility package and run `modelviewr serve`.
"""


def _devtools_document() -> SourceDocument:
    return SourceDocument(
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="sites/projects/Projects Setup",
        source_item_id="onenote:internal-devtools-cli",
        source_url="https://contoso.example.test/onenote/internal-devtools-cli",
        title="Internal DevTools CLI Setup",
        file_name="Internal DevTools CLI Setup.one",
        file_extension="one",
        mime_type="text/html",
        section_path="Projects Setup / 01 Internal DevTools CLI Setup",
        last_modified_utc=datetime(2026, 5, 18, tzinfo=UTC),
        acl_tags=["employees"],
        content_hash="devtools-hash",
        content_text=_DEVTOOLS_TEXT,
        tags=["onenote", "projects-setup", "devtools", "cli", "setup"],
        metadata={
            "notebook_name": "Projects Setup",
            "section_name": "01 Internal DevTools CLI Setup",
            "page_id": "internal-devtools-cli",
        },
    )


def _setup_document(title: str, source_item_id: str, text: str, *, tag: str) -> SourceDocument:
    return SourceDocument(
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="sites/projects/Projects Setup",
        source_item_id=source_item_id,
        source_url=f"https://contoso.example.test/onenote/{source_item_id.removeprefix('onenote:')}",
        title=title,
        file_name=f"{title}.one",
        file_extension="one",
        mime_type="text/html",
        section_path=f"Projects Setup / {title}",
        last_modified_utc=datetime(2026, 5, 18, tzinfo=UTC),
        acl_tags=["employees"],
        content_hash=f"{source_item_id}-hash",
        content_text=text,
        tags=["onenote", "projects-setup", tag, "setup"],
        metadata={
            "notebook_name": "Projects Setup",
            "section_name": title,
            "page_id": source_item_id.removeprefix("onenote:"),
        },
    )


def _modelviewer_document() -> SourceDocument:
    return _setup_document("ModelViewer Setup", "onenote:modelviewer", _MODELVIEWER_TEXT, tag="modelviewer")


def _modelrunner_document() -> SourceDocument:
    return _setup_document("ModelRunner Setup", "onenote:modelrunner", _MODELRUNNER_TEXT, tag="modelrunner")


def _modelviewr_document() -> SourceDocument:
    return _setup_document("ModelViewr Setup", "onenote:modelviewr", _MODELVIEWR_TEXT, tag="modelviewr")


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


class _DefersLlm:
    provider_name = "test"
    model_name = "test"

    async def generate(self, prompt) -> GenerationResult:
        return GenerationResult(provider="test", model="test", answer_text=NO_INFORMATION_ANSWER)

    async def ready(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return [self.model_name]


def _chunks(*documents):
    chunker = TextChunker(AppSettings())
    chunks = []
    for document in documents:
        chunks.extend(chunker.chunk(document))
    return chunks


def _answer(question: str, *documents):
    service = AnswerService(
        llm=_DefersLlm(),
        prompt_builder=PromptBuilder(),
        retriever=_StaticRetriever(_chunks(*documents)),
        access_scope_resolver=AccessScopeResolver(),
        reranker=None,
        min_keyword_overlap=1,
    )
    request = AnswerRequest(question=question, user_context=UserContext(acl_tags=["employees"]), top_k=8)
    return asyncio.run(service.answer(request))


def test_partial_flutter_query_does_not_rank_devtools_first() -> None:
    analysis = analyze_question(FLUTTER_QUERY)
    ranked = rank_chunks_by_question_analysis(analysis, _chunks(flutter_hmi_document(), _devtools_document()), top_k=8)
    assert ranked, "expected ranked chunks"
    assert ranked[0].title == "Flutter Embedded HMI Setup"
    assert all(chunk.title == "Flutter Embedded HMI Setup" for chunk in ranked[:3])


def test_partial_flutter_query_answers_from_flutter_page() -> None:
    response = _answer(FLUTTER_QUERY, flutter_hmi_document(), _devtools_document())
    assert response.answer != NO_INFORMATION_ANSWER
    assert {citation.title for citation in response.citations} == {"Flutter Embedded HMI Setup"}
    assert "DevTools" not in response.answer


def test_flutter_query_does_not_confidently_answer_from_devtools_only() -> None:
    # The right page is missing; the assistant must not present the unrelated
    # DevTools guide as the answer. No-info or an explicit hedge are acceptable;
    # a confident DevTools answer is not.
    response = _answer(FLUTTER_QUERY, _devtools_document())
    assert response.answer == NO_INFORMATION_ANSWER or response.answer.startswith(HEDGED_ANSWER_PREAMBLE)
    confident = (
        response.answer != NO_INFORMATION_ANSWER
        and not response.answer.startswith(HEDGED_ANSWER_PREAMBLE)
    )
    assert not confident


def test_devtools_query_still_answers_from_devtools() -> None:
    # The subject gate must not over-correct: a real DevTools question is answered.
    response = _answer("how to setup the internal devtools cli", _devtools_document())
    assert response.answer != NO_INFORMATION_ANSWER
    assert {citation.title for citation in response.citations} == {"Internal DevTools CLI Setup"}


def test_one_letter_project_name_typo_ranks_intended_page() -> None:
    analysis = analyze_question("how to setup ModelVewer")
    ranked = rank_chunks_by_question_analysis(analysis, _chunks(_modelviewer_document(), _modelrunner_document()), top_k=8)

    assert ranked
    assert ranked[0].title == "ModelViewer Setup"


def test_two_letter_project_name_typo_still_answers_from_intended_page() -> None:
    response = _answer("how to setup ModelVeiwer", _modelviewer_document(), _modelrunner_document())

    assert response.answer != NO_INFORMATION_ANSWER
    assert {citation.title for citation in response.citations} == {"ModelViewer Setup"}
    assert "ModelRunner" not in response.answer


def test_similarly_named_fuzzy_guides_trigger_clarification() -> None:
    response = _answer("how to setup ModelVewer", _modelviewer_document(), _modelviewr_document())

    assert response.clarification is not None
    assert {option.title for option in response.clarification.options} == {
        "ModelViewer Setup",
        "ModelViewr Setup",
    }
    assert response.citations == []
