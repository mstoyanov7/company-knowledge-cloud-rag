from __future__ import annotations

from datetime import UTC, datetime

from rag_api.services.context_builder import build_answer_context
from rag_api.services.query_understanding import analyze_question
from shared_schemas import ChunkDocument, Citation


def test_context_builder_preserves_complete_relevant_paragraphs() -> None:
    first_paragraph = (
        "Deployment starts with selecting the target environment. "
        "The release owner checks migrations, configuration, and rollback notes. "
        "The smoke test must pass before moving to production."
    )
    second_paragraph = (
        "Rollback uses the previous tagged image. "
        "The incident owner updates the release notes and notifies the team."
    )
    trailing_paragraph = " ".join(
        ["This paragraph should be omitted when the budget is small enough."] * 8
    )
    chunk = _chunk(f"{first_paragraph}\n\n{second_paragraph}\n\n{trailing_paragraph}")
    citation = _citation()

    context = build_answer_context(
        analyze_question("How do I deploy?"),
        [chunk],
        [citation],
        max_chars=800,
    )
    rendered = context.context_blocks[0]

    assert first_paragraph in rendered
    assert second_paragraph in rendered
    assert "The release owner checks migrations" in rendered
    assert trailing_paragraph not in rendered


def _chunk(text: str) -> ChunkDocument:
    return ChunkDocument(
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="notebook",
        source_item_id="deployment",
        source_url="https://example.test/deployment",
        title="Deployment Guide",
        section_path="Engineering / Releases",
        last_modified_utc=datetime(2026, 5, 1, tzinfo=UTC),
        acl_tags=["employees"],
        content_hash="hash",
        chunk_id="deployment-0",
        chunk_index=0,
        chunk_text=text,
        embedding_model="token-hash-v1",
        tags=["deployment"],
    )


def _citation() -> Citation:
    return Citation(
        index=1,
        chunk_id="deployment-0",
        source_item_id="deployment",
        chunk_index=0,
        title="Deployment Guide",
        source_system="onenote",
        source_container="notebook",
        source_url="https://example.test/deployment",
        section_path="Engineering / Releases",
        snippet="Deployment starts with selecting the target environment.",
        last_modified_utc=datetime(2026, 5, 1, tzinfo=UTC),
    )
