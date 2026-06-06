"""Regression tests for the corrupted-setup-answer bug.

Covers extraction, chunking, retrieval ranking, context assembly, the
procedure-aware fallback answer, and prompt instructions for the failing query
"how to setup flutter embedded hmi". OneNote-only; no SharePoint.
"""

from __future__ import annotations

import asyncio

from shared_schemas import (
    AccessScope,
    AnswerRequest,
    AppSettings,
    RetrievalMetadata,
    RetrievalResult,
    UserContext,
)

from rag_api.ports import GenerationResult
from rag_api.services import AccessScopeResolver, AnswerService, PromptBuilder
from rag_api.services.context_builder import build_answer_context
from rag_api.services.evidence_grading import DIRECT_ANSWER_FOUND, PARTIAL_ANSWER_FOUND, EvidenceGrader
from rag_api.services.query_understanding import analyze_question
from rag_api.services.retrieval_ranking import chunk_kind_of, rank_chunks_by_question_analysis
from sync_worker.ingestion import TextChunker, compute_content_hash
from sync_worker.ingestion.structure import parse_sections
from sync_worker.onenote.parser import OneNoteHtmlParser

from fixtures.onenote_flutter_hmi import FLUTTER_HMI_HTML, flutter_hmi_document

SETUP_QUESTION = "how to setup flutter embedded hmi"
NO_INFORMATION_ANSWER = "I could not find that information in the available OneNote notes or readable attachments."

SETUP_COMMANDS = (
    "flutter config --enable-linux-desktop",
    "flutter pub get",
    "flutter run -d linux",
)


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #
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
    """LLM that always defers, forcing the extractive fallback path."""

    provider_name = "test"
    model_name = "test"

    async def generate(self, prompt):
        return GenerationResult(provider="test", model="test", answer_text=NO_INFORMATION_ANSWER)

    async def ready(self) -> bool:
        return True

    async def list_models(self):
        return [self.model_name]


def _chunks():
    return TextChunker(AppSettings()).chunk(flutter_hmi_document())


def _answer(question: str, *, acl_tags=("employees",)) -> str:
    chunks = _chunks()
    service = AnswerService(
        llm=NoInfoLlm(),
        prompt_builder=PromptBuilder(),
        retriever=StaticRetriever(chunks),
        access_scope_resolver=AccessScopeResolver(),
        reranker=None,
        min_keyword_overlap=1,
    )
    request = AnswerRequest(question=question, user_context=UserContext(acl_tags=list(acl_tags)), top_k=8)
    return asyncio.run(service.answer(request)).answer


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
def test_extraction_preserves_full_sections() -> None:
    text = OneNoteHtmlParser().parse(FLUTTER_HMI_HTML).text
    for heading in ("Overview", "Prerequisites", "Install", "Configuration", "Run", "Verification", "Troubleshooting"):
        assert f"## {heading}" in text


def test_extraction_keeps_commands_intact_in_fenced_blocks() -> None:
    text = OneNoteHtmlParser().parse(FLUTTER_HMI_HTML).text
    assert "```bash" in text
    for command in SETUP_COMMANDS:
        assert command in text
    # Multi-arg install command is not truncated and the Wayland command keeps its space.
    assert "libgles2-mesa-dev" in text
    assert "WAYLAND_DISPLAY=wayland-0 ./build/linux/x64/release/bundle/flutter_embedded_hmi" in text


def test_extraction_renders_table_rows_readably() -> None:
    text = OneNoteHtmlParser().parse(FLUTTER_HMI_HTML).text
    assert "| Problem | Suggested Check |" in text
    assert "packaged in the bundle" in text  # not corrupted to "kaged"
    assert "kaged" not in text.replace("packaged", "")


def test_extraction_splits_flattened_command_runs_one_per_line() -> None:
    run = (
        "git clone https://github.com/company/renderer-engine.git cd renderer-engine "
        "git submodule update --init --recursive cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug "
        "cmake --build build --config Debug"
    )
    html = f"<html><body><h2>Install</h2><p>{run}</p></body></html>"
    text = OneNoteHtmlParser().parse(html).text
    fenced = text.split("```bash", 1)[1].split("```", 1)[0].strip().splitlines()
    assert fenced == [
        "git clone https://github.com/company/renderer-engine.git",
        "cd renderer-engine",
        "git submodule update --init --recursive",
        "cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug",
        "cmake --build build --config Debug",
    ]


def test_extraction_keeps_package_install_list_on_one_line() -> None:
    html = "<html><body><h2>Install</h2><p>sudo apt install -y clang cmake ninja-build pkg-config</p></body></html>"
    text = OneNoteHtmlParser().parse(html).text
    assert "sudo apt install -y clang cmake ninja-build pkg-config" in text


def test_extraction_has_no_single_letter_garbage_lines() -> None:
    text = OneNoteHtmlParser().parse(FLUTTER_HMI_HTML).text
    for line in text.splitlines():
        stripped = line.strip()
        assert len(stripped) != 1 or stripped in {"|"}, f"stray single-char line: {line!r}"
    # The breadcrumb stays prose, not a command block.
    assert "Flutter / Linux / Wayland / EGL" in text


# --------------------------------------------------------------------------- #
# Chunking
# --------------------------------------------------------------------------- #
def test_chunking_does_not_split_words_or_commands() -> None:
    chunks = _chunks()
    for chunk in chunks:
        # Words are never split (the classic "packaged" -> "pac"/"kaged" bug).
        assert "kaged" not in chunk.chunk_text.replace("packaged", "")
        # Fenced code blocks are never split across a chunk boundary.
        assert chunk.chunk_text.count("```") % 2 == 0
    # Every command survives intact in at least one chunk.
    for command in SETUP_COMMANDS:
        assert any(command in chunk.chunk_text for chunk in chunks)


def test_chunking_groups_procedure_sections_with_chunk_kind() -> None:
    chunks = _chunks()
    procedure = [chunk for chunk in chunks if chunk.chunk_kind == "procedure"]
    assert len(procedure) == 1, "expected exactly one combined procedure chunk"
    text = procedure[0].chunk_text
    for heading in ("Prerequisites", "Install", "Configuration", "Run", "Verification"):
        assert heading in text
    # chunk_kind also mirrored into metadata so it survives the vector-store round-trip.
    assert procedure[0].metadata.get("chunk_kind") == "procedure"


def test_chunking_keeps_code_block_with_its_section() -> None:
    install = [chunk for chunk in _chunks() if chunk.chunk_kind == "install"][0]
    assert "```bash" in install.chunk_text
    for command in ("sudo apt update", "flutter pub get"):
        assert command in install.chunk_text


def test_chunking_keeps_table_rows_together() -> None:
    table = [chunk for chunk in _chunks() if chunk.chunk_kind == "troubleshooting"][0]
    assert table.chunk_text.count("\n|") >= 4  # all rows stay in one chunk


def test_chunking_classifies_metadata_block() -> None:
    chunks = _chunks()
    metadata_chunks = [chunk for chunk in chunks if chunk.chunk_kind == "metadata"]
    assert metadata_chunks, "page metadata should be its own classified chunk"
    assert "Repository: flutter-embedded-hmi" in metadata_chunks[0].chunk_text


def test_structure_parser_classifies_sections() -> None:
    kinds = {section.kind for section in parse_sections(flutter_hmi_document().content_text)}
    assert {"metadata", "prerequisites", "install", "configuration", "run", "verification", "troubleshooting"} <= kinds


# --------------------------------------------------------------------------- #
# Retrieval ranking
# --------------------------------------------------------------------------- #
def test_setup_query_ranks_procedure_above_metadata() -> None:
    analysis = analyze_question(SETUP_QUESTION)
    ranked = rank_chunks_by_question_analysis(analysis, _chunks(), top_k=8)
    kinds = [chunk_kind_of(chunk) for chunk in ranked]
    assert kinds[0] == "procedure"
    if "metadata" in kinds and "procedure" in kinds:
        assert kinds.index("procedure") < kinds.index("metadata")


def test_top_ranked_context_contains_commands_and_sections() -> None:
    analysis = analyze_question(SETUP_QUESTION)
    ranked = rank_chunks_by_question_analysis(analysis, _chunks(), top_k=8)
    top_text = "\n".join(chunk.chunk_text for chunk in ranked[:2])
    for section in ("Install", "Configuration", "Run", "Verification"):
        assert section in top_text
    assert any(command in top_text for command in SETUP_COMMANDS)


# --------------------------------------------------------------------------- #
# Context assembly
# --------------------------------------------------------------------------- #
def test_final_context_contains_clean_procedure_content() -> None:
    from datetime import UTC, datetime

    from shared_schemas import Citation

    analysis = analyze_question(SETUP_QUESTION)
    chunks = rank_chunks_by_question_analysis(analysis, _chunks(), top_k=8)
    citations = [
        Citation(
            index=index,
            chunk_id=chunk.chunk_id,
            source_item_id=chunk.source_item_id,
            chunk_index=chunk.chunk_index,
            title=chunk.title,
            source_system=chunk.source_system,
            source_container=chunk.source_container,
            source_url=chunk.source_url,
            section_path=chunk.section_path,
            snippet="",
            last_modified_utc=datetime(2026, 5, 20, tzinfo=UTC),
        )
        for index, chunk in enumerate(chunks, start=1)
    ]
    context = build_answer_context(analysis, chunks, citations, max_chars=10000)
    blob = "\n".join(context.context_blocks)
    for section in ("Install", "Configuration", "Run", "Verification"):
        assert section in blob
    for command in SETUP_COMMANDS:
        assert command in blob
    assert "kaged" not in blob.replace("packaged", "")


# --------------------------------------------------------------------------- #
# Answer / fallback
# --------------------------------------------------------------------------- #
def test_setup_answer_is_multi_section_and_grounded() -> None:
    answer = _answer(SETUP_QUESTION)
    for section in ("Prerequisites", "Install", "Configuration", "Run", "Verification"):
        assert section in answer
    for command in SETUP_COMMANDS:
        assert command in answer
    # commands stay inside a fenced block with the space preserved
    assert "WAYLAND_DISPLAY=wayland-0 ./build/linux/x64/release/bundle/flutter_embedded_hmi" in answer
    assert "```bash" in answer


def test_setup_answer_does_not_lead_with_metadata() -> None:
    answer = _answer(SETUP_QUESTION)
    assert "Repository:" not in answer
    assert "Owner:" not in answer
    assert "kaged" not in answer.replace("packaged", "")


def test_fallback_answer_is_not_a_single_sentence() -> None:
    answer = _answer(SETUP_QUESTION)
    assert answer.count("####") >= 4  # multiple sections, not one broken line


def test_no_information_behaviour_preserved_for_unrelated_question() -> None:
    answer = _answer("what is the office snack budget for the marketing team")
    assert answer == NO_INFORMATION_ANSWER


# --------------------------------------------------------------------------- #
# Partial-phrasing consistency (logical match, not exact keyword coverage)
# --------------------------------------------------------------------------- #
class _LiteralKeywordGrader:
    """Stand-in for a small local model that grades by literal keyword coverage:
    if the question omits a word from the page's narrow title it calls the page
    only 'related', not 'direct'. The deterministic heuristic must floor this so
    a partial phrasing connects to the same page as the full phrasing."""

    def __init__(self, *, narrow_terms: set[str]) -> None:
        self.narrow_terms = narrow_terms

    async def grade_relevance(self, *, question, question_analysis, chunks):
        question_tokens = set(question.lower().split())
        full_coverage = self.narrow_terms.issubset(question_tokens)
        return {
            "chunks": [
                {
                    "chunk_id": chunk["chunk_id"],
                    "relevance": "direct" if full_coverage else "related",
                    "answers_question": full_coverage,
                    "reason": "literal keyword grade",
                    "confidence": 0.9 if full_coverage else 0.5,
                }
                for chunk in chunks
            ]
        }


def _grade_sufficiency(question: str, grader_llm) -> str:
    analysis = analyze_question(question)
    ranked = rank_chunks_by_question_analysis(analysis, _chunks(), top_k=8)
    grader = EvidenceGrader(llm=grader_llm)
    return asyncio.run(grader.grade(analysis, ranked)).sufficiency


def test_partial_setup_query_is_not_demoted_by_literal_llm_grader() -> None:
    # A literal grader would mark the page only "related" for the short phrasing,
    # which previously produced a "no information" answer. The heuristic floor
    # keeps it answerable so the partial phrasing behaves like the full one.
    grader = _LiteralKeywordGrader(narrow_terms={"embedded", "hmi"})
    full = _grade_sufficiency("how to setup flutter embedded hmi", grader)
    partial = _grade_sufficiency("how to setup flutter", grader)
    assert full in {DIRECT_ANSWER_FOUND, PARTIAL_ANSWER_FOUND}
    assert partial in {DIRECT_ANSWER_FOUND, PARTIAL_ANSWER_FOUND}


def test_unrelated_question_still_rejected_even_if_llm_grader_is_generous() -> None:
    # The floor only protects chunks the heuristic itself is confident about, so
    # an over-generous LLM grade on a genuinely unrelated question is still
    # clamped down to the heuristic verdict (precision is preserved).
    class _GenerousGrader:
        async def grade_relevance(self, *, question, question_analysis, chunks):
            return {
                "chunks": [
                    {
                        "chunk_id": chunk["chunk_id"],
                        "relevance": "direct",
                        "answers_question": True,
                        "reason": "over-generous",
                        "confidence": 0.95,
                    }
                    for chunk in chunks
                ]
            }

    sufficiency = _grade_sufficiency("what is the office snack budget for the marketing team", _GenerousGrader())
    assert sufficiency not in {DIRECT_ANSWER_FOUND, PARTIAL_ANSWER_FOUND}


# --------------------------------------------------------------------------- #
# Prompt instructions
# --------------------------------------------------------------------------- #
def test_prompt_includes_step_by_step_guidance_for_setup_questions() -> None:
    prompt = PromptBuilder().build(SETUP_QUESTION, [], [])
    instruction = prompt.system_instruction
    assert "step-by-step" in instruction
    assert "Prerequisites" in instruction
    assert "Installation commands" in instruction
    assert "Verification" in instruction


def test_prompt_includes_troubleshooting_format_for_troubleshooting_questions() -> None:
    prompt = PromptBuilder().build("egl initialization error on the embedded launcher", [], [])
    assert "Possible cause" in prompt.system_instruction


def test_prompt_supports_checklist_style() -> None:
    prompt = PromptBuilder().build(SETUP_QUESTION, [], [], answer_style="checklist")
    assert "checklist" in prompt.system_instruction.lower()


def test_content_hash_is_stable_for_normalized_text() -> None:
    # Normalization happens before hashing; identical clean text -> identical hash.
    text = flutter_hmi_document().content_text
    assert compute_content_hash(text) == compute_content_hash(text)
