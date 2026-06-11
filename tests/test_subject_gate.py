from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from shared_schemas import ChunkDocument

from rag_api.services.query_understanding import analyze_question
from rag_api.services.retrieval_ranking import subject_supports_confident_grade


def _chunk(*, title: str, text: str, section_path: str = "Project Setups") -> ChunkDocument:
    return ChunkDocument(
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="onenote",
        source_item_id=f"onenote:{title}",
        source_url="https://example.test",
        title=title,
        section_path=section_path,
        last_modified_utc=datetime(2026, 4, 26, tzinfo=UTC),
        acl_tags=["employees"],
        content_hash="hash",
        chunk_id=title,
        chunk_index=0,
        chunk_text=text,
        embedding_model="token-hash-v1",
    )


def _opengl_analysis():
    base = analyze_question("Tell me how to setup open gl model viewer")
    # Pin the distinctive subject so the test does not depend on planner internals.
    return replace(
        base,
        important_entities=("opengl", "model viewer"),
        keyword_queries=("opengl model viewer setup",),
        semantic_queries=("opengl model viewer",),
        must_have_concepts=("opengl", "model", "viewer"),
    )


def test_unrelated_setup_page_is_not_a_confident_match_for_missing_subject() -> None:
    # An OpenGL/model-viewer question must not treat a different product's setup
    # guide as a confident answer just because it shares scaffolding ("setup",
    # "project") and a lone generic body token ("model").
    analysis = _opengl_analysis()
    unrelated = _chunk(
        title="OTA Campaign Simulator Setup",
        text=(
            "## Prerequisites\n- Python 3.10+\n- Docker and Docker Compose\n"
            "- Access to staging backend.\nDefine the campaign model and run the simulator."
        ),
    )
    assert subject_supports_confident_grade(analysis, unrelated) is False


def test_subject_in_title_is_a_confident_match() -> None:
    analysis = _opengl_analysis()
    matching = _chunk(
        title="OpenGL Model Viewer Setup",
        text="## Prerequisites\n- Install the OpenGL model viewer and load a sample model.",
    )
    assert subject_supports_confident_grade(analysis, matching) is True


def test_rich_body_subject_match_is_allowed_without_title() -> None:
    # A genuine body-only answer (subject present substantially, not coincidentally)
    # still qualifies, so paraphrased questions are not over-blocked.
    analysis = _opengl_analysis()
    body_match = _chunk(
        title="Graphics Tooling",
        section_path="Tools",
        text="The OpenGL model viewer renders a model; open the viewer to inspect each model.",
    )
    assert subject_supports_confident_grade(analysis, body_match) is True
