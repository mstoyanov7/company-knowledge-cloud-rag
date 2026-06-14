"""Regression tests for setup answers that dropped page sections.

The "How to setup billing service?" question used to answer only from the
readable attachment's short "Key commands" list, silently dropping the page's
own "Setup Process" preconditions and half of its "Commands" block. The root
cause was classification by *heading keyword*: "Setup Process" and "Commands"
match no keyword, so they were never recognized as procedure content and no
combined procedure chunk was built for the page.

These tests pin the fix: section kind is decided by content *shape* (numbered
steps / command lines), independent of how the author worded the heading, and a
how-to answer surfaces the whole page (preconditions + every command), not just
the best-matching fragment.

OneNote-only. No SharePoint behavior.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from shared_schemas import (
    AccessScope,
    AnswerRequest,
    AppSettings,
    ChunkDocument,
    RetrievalMetadata,
    RetrievalResult,
    SourceDocument,
    UserContext,
)

from rag_api.ports import GenerationResult
from rag_api.services import AccessScopeResolver, AnswerService, PromptBuilder
from rag_api.services.query_understanding import analyze_question
from rag_api.services.retrieval_ranking import chunk_kind_of, rank_chunks_by_question_analysis
from sync_worker.ingestion import TextChunker
from sync_worker.ingestion.structure import parse_sections

SETUP_QUESTION = "How to setup billing service?"
NO_INFORMATION_ANSWER = "I could not find that information in the available OneNote notes or readable attachments."

# Page commands (note: none of these are in the attachment) - the bug dropped them.
PAGE_COMMANDS = (
    "git clone ssh://git.northwind.local/payments/billing-service.git",
    "pip install -e '.[dev]'",
    "nw vault read secret/billing/stripe-test > .env.local",
    "docker compose up -d postgres",
    "alembic upgrade head && pytest tests/smoke",
)
# Preconditions live in "Setup Process" - prose steps with no procedure keyword.
SETUP_PROCESS_STEPS = (
    "Clone the repo and create a virtualenv.",
    "Pull Stripe test secrets from the vault.",
    "Start dependencies with docker compose.",
    "Run migrations and the smoke test.",
)

# Clean Markdown-like text the parser produces from the Billing Service Setup
# page. Headings deliberately use no procedure keyword ("Setup Process",
# "Commands") to prove classification no longer depends on keywords.
BILLING_CLEAN_TEXT = """# Billing Service Setup

Local setup for the billing-service backend (Python/FastAPI).

## Context

Billing Service Setup is the project setup record maintained by Payments Team. billing-service is a FastAPI app backed by PostgreSQL and Stripe.

## Setup Process

1. Clone the repo and create a virtualenv.
2. Pull Stripe test secrets from the vault.
3. Start dependencies with docker compose.
4. Run migrations and the smoke test.

## Key Facts

- billing-service is a FastAPI app backed by PostgreSQL and Stripe.
- It runs locally on port 8020 and uses a seeded test database.
- Stripe test keys are pulled from the Secrets Vault path secret/billing/stripe-test.

## Commands

Run from a clean shell and keep the output with the setup or incident record.

```bash
git clone ssh://git.northwind.local/payments/billing-service.git
cd billing-service && python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
nw vault read secret/billing/stripe-test > .env.local
docker compose up -d postgres
alembic upgrade head && pytest tests/smoke
```
"""

# The readable attachment that previously hijacked the whole answer.
ATTACHMENT_TEXT = """# billing-service README

Quick reference for running billing-service locally.

## Key commands

- alembic upgrade head
- pytest tests/smoke
- uvicorn billing.main:app --port 8020
"""


def _billing_document() -> SourceDocument:
    return SourceDocument(
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="sites/projects/Project Setups",
        source_item_id="onenote:billing-service-setup",
        source_url="https://contoso.example.test/onenote/billing-service-setup",
        title="Billing Service Setup",
        file_name="Billing Service Setup.one",
        file_extension="one",
        mime_type="text/html",
        section_path="Project Setups / 01 Billing Service Setup",
        last_modified_utc=datetime(2026, 5, 20, tzinfo=UTC),
        acl_tags=["employees"],
        content_hash="billing-hash",
        content_text=BILLING_CLEAN_TEXT,
        tags=["onenote", "project-setups", "billing", "setup"],
        metadata={"page_id": "billing-service-setup"},
    )


def _attachment_chunk() -> ChunkDocument:
    return ChunkDocument(
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="sites/projects/Project Setups",
        source_item_id="onenote:billing-readme-attachment",
        source_url="https://contoso.example.test/onenote/billing-readme",
        title="billing-service README",
        section_path="Project Setups / 01 Billing Service Setup",
        last_modified_utc=datetime(2026, 5, 20, tzinfo=UTC),
        acl_tags=["employees"],
        content_hash="billing-readme-hash",
        chunk_id="billing-readme-attachment-chunk-0",
        chunk_index=0,
        chunk_text=ATTACHMENT_TEXT,
        chunk_kind="commands",
        embedding_model="mock",
        tags=["billing"],
        metadata={
            "document_kind": "attachment",
            "chunk_kind": "commands",
            "parent_source_item_id": "onenote:billing-service-setup",
            "parent_title": "Billing Service Setup",
            "attachment_file_name": "01_Billing_Service_Setup__billing-service-readme.md",
        },
    )


def _page_chunks() -> list[ChunkDocument]:
    return TextChunker(AppSettings()).chunk(_billing_document())


def _all_chunks() -> list[ChunkDocument]:
    # Attachment first to reproduce the original bug, where the dense attachment
    # out-ranked the page body and the page sections were dropped.
    return [_attachment_chunk(), *_page_chunks()]


class StaticRetriever:
    name = "static"

    def __init__(self, chunks: list[ChunkDocument]) -> None:
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
    """LLM that always defers, forcing the extractive fallback path."""

    provider_name = "test"
    model_name = "test"

    async def generate(self, prompt):
        return GenerationResult(provider="test", model="test", answer_text=NO_INFORMATION_ANSWER)

    async def ready(self) -> bool:
        return True

    async def list_models(self):
        return [self.model_name]


def _answer(question: str = SETUP_QUESTION) -> str:
    service = AnswerService(
        llm=NoInfoLlm(),
        prompt_builder=PromptBuilder(),
        retriever=StaticRetriever(_all_chunks()),
        access_scope_resolver=AccessScopeResolver(),
        reranker=None,
        min_keyword_overlap=1,
    )
    request = AnswerRequest(question=question, user_context=UserContext(acl_tags=["employees"]), top_k=8)
    return asyncio.run(service.answer(request)).answer


# --------------------------------------------------------------------------- #
# Classification is by content shape, not heading keyword
# --------------------------------------------------------------------------- #
def test_keywordless_headings_are_classified_by_content_shape() -> None:
    kinds = {section.heading_text: section.kind for section in parse_sections(BILLING_CLEAN_TEXT)}
    # Neither "Setup Process" nor "Commands" matches a procedure keyword.
    assert kinds["Setup Process"] == "steps"
    assert kinds["Commands"] == "commands"
    # A prose bullet list of facts must NOT be mistaken for a procedure.
    assert kinds["Key Facts"] == "section"


def test_alternative_wording_still_recognized_as_procedure() -> None:
    text = """## Walkthrough

1. Grab the source and make a venv.
2. Drop the secrets file in place.

## Snippets

```bash
docker compose up -d
```
"""
    kinds = {section.heading_text: section.kind for section in parse_sections(text)}
    assert kinds["Walkthrough"] == "steps"  # purely from the numbered list
    assert kinds["Snippets"] == "commands"  # purely from the code block


def test_combined_procedure_chunk_merges_steps_and_commands() -> None:
    procedure = [chunk for chunk in _page_chunks() if chunk.chunk_kind == "procedure"]
    assert len(procedure) == 1, "expected one combined procedure chunk for the page"
    text = procedure[0].chunk_text
    assert any(step in text for step in SETUP_PROCESS_STEPS)
    assert all(command in text for command in PAGE_COMMANDS)
    assert procedure[0].metadata.get("chunk_kind") == "procedure"


# --------------------------------------------------------------------------- #
# Ranking: the page procedure wins over the dense attachment
# --------------------------------------------------------------------------- #
def test_page_procedure_outranks_attachment() -> None:
    analysis = analyze_question(SETUP_QUESTION)
    ranked = rank_chunks_by_question_analysis(analysis, _all_chunks(), top_k=8)
    assert chunk_kind_of(ranked[0]) == "procedure"


# --------------------------------------------------------------------------- #
# Answer completeness: nothing valuable is dropped
# --------------------------------------------------------------------------- #
def test_answer_includes_setup_process_preconditions() -> None:
    answer = _answer()
    assert any(step in answer for step in SETUP_PROCESS_STEPS), "Setup Process preconditions were dropped"


def test_answer_includes_every_page_command_not_just_the_attachment() -> None:
    answer = _answer()
    for command in PAGE_COMMANDS:
        assert command in answer, f"missing command from the page: {command!r}"
