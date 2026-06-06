import time
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
import re
from textwrap import shorten

from rag_api.ports import DocumentMetadataPort, LlmPort, RerankerPort, RetrievalPort
from rag_api.services.access_scope import AccessScopeResolver
from rag_api.services.clarification import clarification_answer_text, detect_clarification
from rag_api.services.context_builder import build_answer_context
from rag_api.services.conversation_context import contextualize_question
from rag_api.services.evidence_grading import (
    DIRECT_ANSWER_FOUND,
    EvidenceAssessment,
    EvidenceGrade,
    EvidenceGrader,
    PARTIAL_ANSWER_FOUND,
    RELATED_BUT_NOT_ENOUGH,
)
from rag_api.services.prompt_builder import PromptBuilder
from rag_api.services.query_understanding import QuestionAnalysis, QueryPlanner, canonical_key_phrase
from rag_api.services.retrieval_ranking import (
    analysis_relevance_score,
    chunk_kind_of,
    chunk_relevance_breakdown,
    fuzzy_metadata_relevance_score,
    is_procedure_question,
    rank_chunks_by_question_analysis,
)
from rag_api.services.security_audit import SecurityAuditLogger
from rag_api.services.topic_service import AnswerTopicScope, TopicService
from shared_schemas import (
    AccessScope,
    AnswerMetadata,
    AnswerRequest,
    AnswerResponse,
    Citation,
    Clarification,
    DownloadLink,
    RetrievalMetadata,
    RetrievalRequest,
    RetrievalResult,
    SourceAttachment,
    SourceDocument,
)

try:
    from opentelemetry import metrics, trace
except ModuleNotFoundError:  # pragma: no cover - optional runtime dependency
    metrics = None
    trace = None


NO_INFORMATION_ANSWER = "I could not find that information in the available OneNote notes or readable attachments."
# Friendly caveat used when the notes hold something topically related but not a
# confident, direct answer. Keeps the assistant helpful instead of dead-ending on
# "no information" whenever the match is not 100% certain.
HEDGED_ANSWER_PREAMBLE = (
    "I couldn't find a definitive answer to your exact question, but here's some "
    "related information from the notes that may be helpful:"
)
logger = logging.getLogger(__name__)
_GENERIC_ENTITY_TERMS = {
    "any",
    "company",
    "detail",
    "details",
    "information",
    "info",
    "main",
    "note",
    "notes",
    "policy",
    "question",
    "rule",
    "rules",
    "there",
}
# Tokens too generic to justify surfacing a note as "partially related" on their
# own. A hedge needs a stronger topical link than one of these shared words, so a
# coincidental overlap (e.g. "paid" between a salary question and a leave note)
# does not trigger a misleading near-answer.
_GENERIC_HEDGE_TERMS = _GENERIC_ENTITY_TERMS | {
    "date",
    "day",
    "days",
    "page",
    "pages",
    "paid",
    "section",
    "sections",
    "time",
    "topic",
    # Generic how-to scaffolding: shared "setup"/"project"/"guide" words do not
    # make an unrelated guide "partially related" to the question's real subject.
    "setup",
    "install",
    "installation",
    "configure",
    "configuration",
    "config",
    "guide",
    "tutorial",
    "step",
    "steps",
    "process",
    "procedure",
    "instruction",
    "instructions",
    "documentation",
    "overview",
    "project",
    "projects",
    "create",
    "build",
    "run",
    "reference",
}


def _is_attachment_chunk(chunk) -> bool:
    return bool((chunk.metadata or {}).get("document_kind") == "attachment")


def _chunk_parent_page_id(chunk) -> str:
    """The page a chunk belongs to - the parent page for readable attachments,
    so an attachment is treated as part of its OneNote page."""
    metadata = chunk.metadata or {}
    if metadata.get("document_kind") == "attachment":
        return str(metadata.get("parent_source_item_id") or chunk.source_item_id)
    return chunk.source_item_id


def _chunk_in_focus(chunk, focus_ids: set[str]) -> bool:
    return chunk.source_item_id in focus_ids or _chunk_parent_page_id(chunk) in focus_ids


@dataclass(frozen=True, slots=True)
class InventoryRequestMatch:
    mode: str
    target_tokens: tuple[str, ...]
    target_label: str
    section_inventory: bool = False


class AnswerService:
    def __init__(
        self,
        *,
        llm: LlmPort,
        prompt_builder: PromptBuilder,
        retriever: RetrievalPort,
        metadata: DocumentMetadataPort | None = None,
        access_scope_resolver: AccessScopeResolver,
        reranker: RerankerPort | None = None,
        retrieval_candidate_multiplier: int = 3,
        min_keyword_overlap: int = 1,
        audit_logger: SecurityAuditLogger | None = None,
        query_planner: QueryPlanner | None = None,
        evidence_grader: EvidenceGrader | None = None,
        topic_service: TopicService | None = None,
        debug_enabled: bool = False,
        clarify_enabled: bool = True,
        clarify_closeness_ratio: float = 0.6,
        clarify_max_options: int = 5,
    ) -> None:
        self.llm = llm
        self.prompt_builder = prompt_builder
        self.retriever = retriever
        self.metadata = metadata
        self.access_scope_resolver = access_scope_resolver
        self.reranker = reranker
        self.retrieval_candidate_multiplier = max(1, retrieval_candidate_multiplier)
        self.min_keyword_overlap = max(0, min_keyword_overlap)
        self.audit_logger = audit_logger
        self.query_planner = query_planner or QueryPlanner()
        self.evidence_grader = evidence_grader or EvidenceGrader(llm=llm)
        self.topic_service = topic_service
        self.debug_enabled = debug_enabled
        self.clarify_enabled = clarify_enabled
        self.clarify_closeness_ratio = clarify_closeness_ratio
        self.clarify_max_options = max(2, clarify_max_options)
        self.tracer = trace.get_tracer("rag_api.answer") if trace else None
        self.answer_latency_ms = (
            metrics.get_meter("rag_api.answer").create_histogram("rag_answer_latency_ms") if metrics else None
        )
        meter = metrics.get_meter("rag_api.answer") if metrics else None
        self.retrieval_latency_ms = meter.create_histogram("rag_retrieval_latency_ms") if meter else None
        self.completion_latency_ms = meter.create_histogram("rag_completion_latency_ms") if meter else None
        self.freshness_delay_ms = meter.create_histogram("rag_freshness_delay_ms") if meter else None
        self.citation_count = meter.create_histogram("rag_citation_count") if meter else None

    async def answer(self, request: AnswerRequest) -> AnswerResponse:
        started = time.perf_counter()
        span = self.tracer.start_as_current_span("rag.answer") if self.tracer else nullcontext()
        with span:
            topic_scope = self.topic_service.scope_answer_request(request) if self.topic_service else None
            effective_request = _request_with_topic_scope(request, topic_scope)
            suggested_questions = list(topic_scope.topic.suggested_questions) if topic_scope else []
            access_scope = self.access_scope_resolver.resolve(
                effective_request.user_context,
                effective_request.source_filters,
            )
            effective_question = contextualize_question(request.question, request.history)
            question_analysis = await self.query_planner.plan(effective_question)
            self._debug_event(
                "query_plan",
                original_question=request.question,
                effective_question=effective_question,
                history_turns=len(request.history),
                topic_id=topic_scope.topic.id if topic_scope else None,
                plan=_question_analysis_debug_payload(question_analysis),
            )
            inventory_response = self._answer_inventory_question(
                request=effective_request,
                question_analysis=question_analysis,
                topic_scope=topic_scope,
                access_scope=access_scope,
                suggested_questions=suggested_questions,
                started=started,
            )
            if inventory_response is not None:
                return inventory_response
            candidate_top_k = request.top_k
            if self.reranker:
                candidate_top_k = max(request.top_k, request.top_k * self.retrieval_candidate_multiplier)
            retrieval_started = time.perf_counter()
            retrieval_result = await self._retrieve_for_question_analysis(
                question_analysis=question_analysis,
                request=effective_request,
                top_k=candidate_top_k,
                access_scope=access_scope,
                topic_scope=topic_scope,
            )
            retrieval_result.metadata.duration_ms = int((time.perf_counter() - retrieval_started) * 1000)
            retrieval_result.metadata.topic_id = topic_scope.topic.id if topic_scope else None
            retrieval_result.metadata.topic_tags = list(topic_scope.retrieval_terms) if topic_scope else []
            chunks = retrieval_result.chunks
            if request.focus_source_item_ids:
                # The user already picked a page in answer to a clarification;
                # keep only that page so the answer is drawn from their choice.
                # Readable attachments belong to their parent page, so a chunk
                # whose parent_source_item_id matches the focus stays eligible.
                focus_ids = set(request.focus_source_item_ids)
                chunks = [chunk for chunk in chunks if _chunk_in_focus(chunk, focus_ids)]
                retrieval_result.chunks = chunks
            self._debug_event("retrieved_chunks", chunks=_chunk_debug_payload(chunks))
            if self.reranker:
                chunks = self.reranker.rerank(
                    _topic_aware_query(question_analysis.search_text, topic_scope),
                    chunks,
                    top_k=candidate_top_k,
                )
                retrieval_result.metadata.reranker = self.reranker.name
                retrieval_result.metadata.requested_top_k = request.top_k
            chunks = self._filter_relevant_chunks(question_analysis, chunks)
            chunks = _prioritize_topic_chunks(chunks, topic_scope)
            chunks = rank_chunks_by_question_analysis(question_analysis, chunks, top_k=request.top_k)
            self._debug_event(
                "reranked_chunks",
                chunks=_chunk_debug_payload(chunks),
                scores=[
                    {
                        "chunk_id": chunk.chunk_id,
                        "title": chunk.title,
                        **chunk_relevance_breakdown(question_analysis, chunk),
                    }
                    for chunk in chunks
                ],
            )
            evidence_assessment = await self.evidence_grader.grade(question_analysis, chunks)
            self._debug_event(
                "evidence_grades",
                sufficiency=evidence_assessment.sufficiency,
                grades=[_grade_debug_payload(grade) for grade in evidence_assessment.grades],
            )
            graded_chunks = chunks
            chunks = list(evidence_assessment.selected_chunks)
            retrieval_result.metadata.returned_count = len(chunks)
            retrieval_result.metadata.evidence_sufficiency = evidence_assessment.sufficiency
            retrieval_result.metadata.relevance_grades = [
                {
                    "chunk_id": grade.chunk_id,
                    "relevance": grade.relevance,
                    "answers_question": grade.answers_question,
                    "confidence": grade.confidence,
                }
                for grade in evidence_assessment.grades
            ]
            if self.clarify_enabled and not request.focus_source_item_ids:
                clarification = detect_clarification(
                    question_analysis,
                    graded_chunks,
                    evidence_assessment.grades,
                    closeness_ratio=self.clarify_closeness_ratio,
                    max_options=self.clarify_max_options,
                )
                if clarification is not None:
                    self._debug_event(
                        "clarification",
                        options=[option.title for option in clarification.options],
                    )
                    return self._build_clarification_response(
                        clarification=clarification,
                        retrieval_result=retrieval_result,
                        request=effective_request,
                        suggested_questions=suggested_questions,
                        started=started,
                    )
            answer_accepted = (
                evidence_assessment.sufficiency in {DIRECT_ANSWER_FOUND, PARTIAL_ANSWER_FOUND} and bool(chunks)
            )
            if not answer_accepted:
                # Before giving up, try to surface anything topically related with
                # an explicit caveat. Only a genuine empty-handed result should
                # ever reach the bare "no information" reply.
                hedged_response = self._build_hedged_response(
                    question_analysis=question_analysis,
                    graded_chunks=graded_chunks,
                    evidence_assessment=evidence_assessment,
                    retrieval_result=retrieval_result,
                    request=effective_request,
                    suggested_questions=suggested_questions,
                    started=started,
                )
                if hedged_response is not None:
                    self._debug_event(
                        "evidence_hedged",
                        sufficiency=evidence_assessment.sufficiency,
                        citations=[citation.title for citation in hedged_response.citations],
                    )
                    return hedged_response
                self._debug_event("evidence_rejected", sufficiency=evidence_assessment.sufficiency)
                citations: list[Citation] = []
                self._audit_retrieval(effective_request, retrieval_result, citations)
                duration_ms = int((time.perf_counter() - started) * 1000)
                return AnswerResponse(
                    answer=NO_INFORMATION_ANSWER,
                    citations=[],
                    retrieval_meta=retrieval_result.metadata,
                    metadata=AnswerMetadata(
                        provider=self.llm.provider_name,
                        model=self.llm.model_name,
                        retrieval_strategy=retrieval_result.metadata.strategy,
                        retrieved_chunk_count=0,
                        source_systems=[],
                        duration_ms=duration_ms,
                        retrieval_latency_ms=retrieval_result.metadata.duration_ms,
                        completion_latency_ms=0,
                        freshness_delay_ms=None,
                        citation_count=0,
                    ),
                    suggested_questions=suggested_questions,
                )
            citations = self._build_citations(chunks)
            self._audit_retrieval(effective_request, retrieval_result, citations)
            answer_context = build_answer_context(
                question_analysis,
                chunks,
                citations,
                max_chars=_context_budget_for_depth(request.answer_depth),
            )
            self._debug_event(
                "selected_context",
                topic_id=topic_scope.topic.id if topic_scope else None,
                answer_depth=request.answer_depth,
                answer_style=request.answer_style,
                chunk_kinds=[chunk_kind_of(chunk) for chunk in chunks],
                source_titles=list(answer_context.source_titles),
                context_chars=answer_context.total_chars,
                context_blocks=list(answer_context.context_blocks),
            )
            prompt = self.prompt_builder.build(
                effective_question,
                chunks,
                citations,
                question_analysis=question_analysis,
                answer_context=answer_context,
                topic_name=topic_scope.topic.name if topic_scope else None,
                topic_description=topic_scope.topic.description if topic_scope else None,
                answer_depth=request.answer_depth,
                answer_style=request.answer_style,
            )
            completion_started = time.perf_counter()
            generation = await self.llm.generate(prompt)
            answer_text, citations = self._guard_generated_answer(
                question=effective_question,
                question_analysis=question_analysis,
                answer_text=generation.answer_text,
                chunks=chunks,
                citations=citations,
                evidence_assessment=evidence_assessment,
            )
            answer_text = _strip_inline_citation_markers(answer_text)
            answer_text = _strip_trailing_source_line(answer_text)
            answer_text = _normalize_no_information_text(answer_text)
            validation_passed = _final_answer_is_valid(answer_text, citations, evidence_assessment)
            self._debug_event("final_answer_validation", passed=validation_passed, answer_preview=answer_text[:300])
            downloads: list[DownloadLink] = []
            if not validation_passed:
                answer_text = NO_INFORMATION_ANSWER
                citations = []
            else:
                downloads = self._downloads_for_answer(question_analysis, chunks, citations)
                answer_text = _append_downloads_section(answer_text, downloads)
            completion_latency_ms = int((time.perf_counter() - completion_started) * 1000)
            duration_ms = int((time.perf_counter() - started) * 1000)
            freshness_delay_ms = _freshness_delay_ms(citations)
            if self.answer_latency_ms:
                self.answer_latency_ms.record(
                    duration_ms,
                    {"provider": generation.provider, "retriever": retrieval_result.metadata.strategy},
                )
            if self.retrieval_latency_ms:
                self.retrieval_latency_ms.record(
                    retrieval_result.metadata.duration_ms,
                    {"retriever": retrieval_result.metadata.strategy},
                )
            if self.completion_latency_ms:
                self.completion_latency_ms.record(completion_latency_ms, {"provider": generation.provider})
            if self.freshness_delay_ms and freshness_delay_ms is not None:
                self.freshness_delay_ms.record(freshness_delay_ms, {"retriever": retrieval_result.metadata.strategy})
            if self.citation_count:
                self.citation_count.record(len(citations), {"retriever": retrieval_result.metadata.strategy})

            return AnswerResponse(
                answer=answer_text,
                citations=citations,
                downloads=downloads,
                retrieval_meta=retrieval_result.metadata,
                metadata=AnswerMetadata(
                    provider=generation.provider,
                    model=generation.model,
                    retrieval_strategy=retrieval_result.metadata.strategy,
                    retrieved_chunk_count=len(citations),
                    source_systems=sorted({citation.source_system for citation in citations}),
                    duration_ms=duration_ms,
                    retrieval_latency_ms=retrieval_result.metadata.duration_ms,
                    completion_latency_ms=completion_latency_ms,
                    freshness_delay_ms=freshness_delay_ms,
                    citation_count=len(citations),
                ),
                suggested_questions=suggested_questions,
            )

    def _build_hedged_response(
        self,
        *,
        question_analysis: QuestionAnalysis,
        graded_chunks: list,
        evidence_assessment: EvidenceAssessment,
        retrieval_result: RetrievalResult,
        request: AnswerRequest,
        suggested_questions: list[str],
        started: float,
    ) -> AnswerResponse | None:
        """Build a friendly "partially related" answer instead of a flat refusal.

        When grading found content topically connected to the question but not
        confident enough to be a direct or partial answer, we still help: extract
        the closest related notes and prefix a clear caveat so the user knows it
        is not a guaranteed match. Returns ``None`` when nothing is genuinely
        related, so the caller falls back to the strict no-information reply (the
        only case the user should ever see that message).
        """
        related_chunks = _related_chunks_for_hedge(question_analysis, evidence_assessment.grades, graded_chunks)
        if not related_chunks:
            return None
        citations = self._build_citations(related_chunks)
        body, used_citations = _extractive_response(question_analysis, related_chunks, citations)
        body = _strip_inline_citation_markers(body)
        if not used_citations or not body.strip() or _is_no_information_text(body):
            return None
        answer_text = _hedged_answer_text(body)
        self._audit_retrieval(request, retrieval_result, used_citations)
        retrieval_result.metadata.returned_count = len(used_citations)
        duration_ms = int((time.perf_counter() - started) * 1000)
        return AnswerResponse(
            answer=answer_text,
            citations=used_citations,
            retrieval_meta=retrieval_result.metadata,
            metadata=AnswerMetadata(
                provider=self.llm.provider_name,
                model=self.llm.model_name,
                retrieval_strategy=retrieval_result.metadata.strategy,
                retrieved_chunk_count=len(used_citations),
                source_systems=sorted({citation.source_system for citation in used_citations}),
                duration_ms=duration_ms,
                retrieval_latency_ms=retrieval_result.metadata.duration_ms,
                completion_latency_ms=0,
                freshness_delay_ms=_freshness_delay_ms(used_citations),
                citation_count=len(used_citations),
            ),
            suggested_questions=suggested_questions,
        )

    def _build_clarification_response(
        self,
        *,
        clarification: Clarification,
        retrieval_result: RetrievalResult,
        request: AnswerRequest,
        suggested_questions: list[str],
        started: float,
    ) -> AnswerResponse:
        """Return a quiz-style follow-up asking which page the user means.

        Carries no citations - the candidate pages live in ``clarification`` so
        the client can render pickable options - and is returned directly so the
        answer-grounding guards do not strip the prompt.
        """
        retrieval_result.metadata.returned_count = 0
        retrieval_result.metadata.evidence_sufficiency = "AMBIGUOUS_MULTIPLE_TOPICS"
        self._audit_retrieval(request, retrieval_result, [])
        duration_ms = int((time.perf_counter() - started) * 1000)
        return AnswerResponse(
            answer=clarification_answer_text(clarification),
            citations=[],
            retrieval_meta=retrieval_result.metadata,
            metadata=AnswerMetadata(
                provider=self.llm.provider_name,
                model=self.llm.model_name,
                retrieval_strategy=retrieval_result.metadata.strategy,
                retrieved_chunk_count=0,
                source_systems=[],
                duration_ms=duration_ms,
                retrieval_latency_ms=retrieval_result.metadata.duration_ms,
                completion_latency_ms=0,
                freshness_delay_ms=None,
                citation_count=0,
            ),
            suggested_questions=suggested_questions,
            clarification=clarification,
        )

    def _debug_event(self, event: str, **fields) -> None:
        if not self.debug_enabled:
            return
        logger.info("rag_debug %s", json.dumps({"event": event, **fields}, default=str, ensure_ascii=False))

    def _answer_inventory_question(
        self,
        *,
        request: AnswerRequest,
        question_analysis: QuestionAnalysis,
        topic_scope: AnswerTopicScope | None,
        access_scope,
        suggested_questions: list[str],
        started: float,
    ) -> AnswerResponse | None:
        match = _inventory_request_match(question_analysis, topic_scope)
        if match is None or self.metadata is None:
            return None

        documents = _allowed_inventory_documents(self.metadata.list_documents(), access_scope)
        matched_documents = _matching_inventory_documents(documents, match)
        if not matched_documents:
            return _inventory_response(
                answer=_no_inventory_answer(match),
                documents=[],
                request=request,
                access_scope=access_scope,
                candidate_count=len(documents),
                started=started,
                suggested_questions=suggested_questions,
            )

        answer = _format_inventory_answer(match, matched_documents)
        return _inventory_response(
            answer=answer,
            documents=matched_documents,
            request=request,
            access_scope=access_scope,
            candidate_count=len(documents),
            started=started,
            suggested_questions=suggested_questions,
        )

    async def _retrieve_for_question_analysis(
        self,
        *,
        question_analysis: QuestionAnalysis,
        request: AnswerRequest,
        top_k: int,
        access_scope,
        topic_scope: AnswerTopicScope | None = None,
    ) -> RetrievalResult:
        results: list[RetrievalResult] = []
        retrieval_queries: list[str] = []
        for query in question_analysis.search_queries:
            topic_query = _topic_aware_query(query, topic_scope)
            retrieval_queries.append(topic_query)
            retrieval_request = RetrievalRequest(
                question=topic_query,
                user_context=request.user_context,
                top_k=top_k,
                source_filters=request.source_filters,
                access_scope=access_scope,
                topic_id=topic_scope.topic.id if topic_scope else None,
                topic_tags=list(topic_scope.retrieval_terms) if topic_scope else [],
                focus_source_item_ids=list(request.focus_source_item_ids),
            )
            results.append(await self.retriever.retrieve(retrieval_request))
        merged = _merge_retrieval_results(question_analysis, results, top_k=top_k)
        merged.metadata.query_variants = retrieval_queries
        return merged

    def _filter_relevant_chunks(self, question_analysis: QuestionAnalysis, chunks: list) -> list:
        if self.min_keyword_overlap <= 0:
            return chunks
        question_tokens = _content_tokens(question_analysis.search_text)
        if not question_tokens:
            return []
        relevant = []
        for chunk in chunks:
            if _is_value_reference_only(question_analysis.search_text, chunk.chunk_text):
                continue
            relevance_score = analysis_relevance_score(question_analysis, chunk)
            if relevance_score >= self.min_keyword_overlap:
                relevant.append((relevance_score, chunk))
        relevant.sort(key=lambda item: (-item[0], -item[1].score, item[1].title, item[1].chunk_index))
        return [chunk for _relevance_score, chunk in relevant]

    def _guard_generated_answer(
        self,
        *,
        question: str,
        question_analysis: QuestionAnalysis,
        answer_text: str,
        chunks: list,
        citations: list[Citation],
        evidence_assessment: EvidenceAssessment | None = None,
    ) -> tuple[str, list[Citation]]:
        normalized_answer = answer_text.strip()
        retrieval_question = question_analysis.search_text
        if _is_no_information_text(normalized_answer):
            if citations:
                return _extractive_response(question_analysis, chunks, citations)
            return NO_INFORMATION_ANSWER, []
        if not citations:
            return NO_INFORMATION_ANSWER, []

        cited_indexes = {int(index) for index in re.findall(r"\[(\d+)\]", normalized_answer)}
        valid_indexes = {citation.index for citation in citations}
        used_indexes = cited_indexes.intersection(valid_indexes)
        if not used_indexes:
            if not _answer_matches_current_question(question_analysis, normalized_answer, chunks):
                return _extractive_response(question_analysis, chunks, citations)
            if _answer_is_grounded_enough(retrieval_question, normalized_answer, chunks) and _answer_covers_selected_context(
                retrieval_question,
                normalized_answer,
                chunks,
            ):
                selected_citations = _select_fallback_citations(retrieval_question, chunks, citations)
                return _ensure_markdown_answer(
                    _append_missing_citation(normalized_answer, selected_citations),
                    selected_citations,
                ), selected_citations
            return _extractive_response(question_analysis, chunks, citations)

        chunks_by_index = {index: chunk for index, chunk in enumerate(chunks, start=1)}
        cited_chunks = [chunks_by_index[index] for index in sorted(used_indexes) if index in chunks_by_index]
        if _is_title_only_answer(normalized_answer, cited_chunks):
            return _extractive_response(question_analysis, chunks, citations)
        if not _answer_matches_current_question(question_analysis, normalized_answer, chunks):
            return _extractive_response(question_analysis, chunks, citations)

        allowed_tokens = _content_tokens(question)
        allowed_tokens.update(_content_tokens(retrieval_question))
        for chunk in cited_chunks:
            allowed_tokens.update(_content_tokens(chunk.title))
            allowed_tokens.update(_content_tokens(chunk.section_path or ""))
            allowed_tokens.update(_content_tokens(chunk.chunk_text))
            allowed_tokens.update(_content_tokens(" ".join(chunk.tags)))

        answer_tokens = _content_tokens(re.sub(r"\[\d+\]", "", normalized_answer))
        unsupported_tokens = answer_tokens.difference(allowed_tokens)
        if _has_material_unsupported_content(unsupported_tokens, answer_tokens):
            return _extractive_response(question_analysis, chunks, citations)
        if _answer_lacks_expected_value(retrieval_question, normalized_answer, chunks):
            return _extractive_response(question_analysis, chunks, citations)
        if _answer_is_too_narrow_for_structured_question(retrieval_question, normalized_answer, cited_chunks):
            return _extractive_response(question_analysis, chunks, citations)

        used_citations = [citation for citation in citations if citation.index in used_indexes]
        return _ensure_markdown_answer(normalized_answer, used_citations), used_citations

    def _build_citations(self, chunks: list) -> list[Citation]:
        citations: list[Citation] = []
        for index, chunk in enumerate(chunks, start=1):
            chunk_metadata = chunk.metadata or {}
            citation_metadata = {
                **chunk_metadata,
                "content_hash": chunk.content_hash,
                "score": chunk.score,
                "tags": chunk.tags,
            }
            if chunk_metadata.get("document_kind") == "attachment":
                parent_title = _optional_string(chunk_metadata.get("parent_title")) or chunk.title
                file_name = (
                    _optional_string(chunk_metadata.get("attachment_file_name"))
                    or _optional_string(chunk_metadata.get("file_name"))
                    or chunk.title
                )
                citation_metadata["citation_page_title"] = parent_title
                citation_metadata["citation_file_name"] = file_name
                title = f"Page: {parent_title} | File: {file_name}"
            else:
                title = chunk.title
            citations.append(
                Citation(
                    index=index,
                    chunk_id=chunk.chunk_id,
                    source_item_id=chunk.source_item_id,
                    chunk_index=chunk.chunk_index,
                    title=title,
                    source_system=chunk.source_system,
                    source_container=chunk.source_container,
                    source_url=chunk.source_url,
                    section_path=chunk.section_path,
                    snippet=shorten(chunk.chunk_text, width=180, placeholder="..."),
                    last_modified_utc=chunk.last_modified_utc,
                    last_edited_by=_metadata_string(
                        chunk.metadata,
                        "last_edited_by",
                        "lastEditedBy",
                        "last_modified_by",
                        "lastModifiedBy",
                    ),
                    client_url=_metadata_string(
                        chunk.metadata,
                        "client_url",
                        "oneNoteClientUrl",
                        "onenote_client_url",
                    ),
                    metadata=citation_metadata,
                )
            )
        return citations

    def _downloads_for_answer(
        self,
        question_analysis: QuestionAnalysis,
        chunks: list,
        citations: list[Citation],
    ) -> list[DownloadLink]:
        downloads_by_id: dict[str, DownloadLink] = {}

        def add(download: DownloadLink | None) -> None:
            if download is not None:
                downloads_by_id.setdefault(download.download_id, download)

        chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        cited_chunks_by_id = {
            citation.chunk_id: chunk
            for citation in citations
            if (chunk := chunks_by_id.get(citation.chunk_id)) is not None
        }
        parent_source_item_ids: set[str] = set()
        for citation in citations:
            metadata = citation.metadata or {}
            if metadata.get("document_kind") == "attachment":
                add(_download_from_metadata(metadata))
                parent_source_item_id = _optional_string(metadata.get("parent_source_item_id"))
                if parent_source_item_id:
                    parent_source_item_ids.add(parent_source_item_id)
            else:
                parent_source_item_ids.add(citation.source_item_id)
            chunk = cited_chunks_by_id.get(citation.chunk_id)
            if chunk is not None:
                for payload in _attachment_refs(chunk):
                    add(_download_from_metadata(payload))

        if self.metadata is not None and parent_source_item_ids:
            for attachment in self.metadata.list_attachments(sorted(parent_source_item_ids)):
                add(_download_from_attachment(attachment))

        return list(downloads_by_id.values())

    def _audit_retrieval(self, request: AnswerRequest, retrieval_result, citations: list[Citation]) -> None:
        if self.audit_logger is None:
            return
        access_scope = retrieval_result.metadata.access_scope
        if retrieval_result.metadata.filtered_count:
            self.audit_logger.record(
                "retrieval_denial",
                "filtered",
                actor_user_id=access_scope.user_id,
                tenant_id=access_scope.tenant_id,
                resource_type="chunk",
                metadata={
                    "filtered_count": retrieval_result.metadata.filtered_count,
                    "source_filters": retrieval_result.metadata.source_filters,
                    "question_hash": _safe_question_hash(request.question),
                },
            )
        for citation in citations:
            self.audit_logger.record(
                "cited_source_access",
                "allowed",
                actor_user_id=access_scope.user_id,
                tenant_id=access_scope.tenant_id,
                resource_type=citation.source_system,
                resource_id=citation.source_item_id,
                metadata={
                    "chunk_id": citation.chunk_id,
                    "chunk_index": citation.chunk_index,
                    "title": citation.title,
                },
            )


def _safe_question_hash(question: str) -> str:
    import hashlib

    return hashlib.sha256(question.encode("utf-8")).hexdigest()


def _question_analysis_debug_payload(question_analysis: QuestionAnalysis) -> dict[str, object]:
    return {
        "detected_language": question_analysis.detected_language,
        "answer_type": question_analysis.answer_type,
        "important_entities": list(question_analysis.important_entities),
        "key_phrases": list(question_analysis.key_phrases),
        "rewritten_question": question_analysis.rewritten_question,
        "semantic_queries": list(question_analysis.semantic_queries),
        "keyword_queries": list(question_analysis.keyword_queries),
        "must_have_concepts": list(question_analysis.must_have_concepts),
        "avoid_concepts": list(question_analysis.avoid_concepts),
        "expected_evidence_type": question_analysis.expected_evidence_type,
        "specificity": question_analysis.specificity,
    }


def _chunk_debug_payload(chunks: list) -> list[dict[str, object]]:
    return [
        {
            "chunk_id": chunk.chunk_id,
            "title": chunk.title,
            "section_path": chunk.section_path,
            "score": chunk.score,
            "preview": shorten(chunk.chunk_text.replace("\n", " "), width=180, placeholder="..."),
        }
        for chunk in chunks
    ]


def _grade_debug_payload(grade: EvidenceGrade) -> dict[str, object]:
    return {
        "chunk_id": grade.chunk_id,
        "relevance": grade.relevance,
        "answers_question": grade.answers_question,
        "confidence": grade.confidence,
        "reason": grade.reason,
    }


_INVENTORY_TRIGGER_NOUNS = {
    "benefit",
    "document",
    "guide",
    "note",
    "page",
    "policy",
    "project",
    "section",
    "setup",
    "topic",
}

_INVENTORY_GENERIC_TERMS = {
    "accessible",
    "all",
    "available",
    "base",
    "company",
    "count",
    "document",
    "exist",
    "existing",
    "found",
    "knowledge",
    "list",
    "many",
    "note",
    "number",
    "page",
    "section",
    "show",
    "there",
    "total",
}


def _inventory_request_match(
    question_analysis: QuestionAnalysis,
    topic_scope: AnswerTopicScope | None,
) -> InventoryRequestMatch | None:
    normalized = _normalized_words(question_analysis.original_question)
    raw_tokens = set(normalized.split())
    tokens = _content_tokens(question_analysis.original_question)
    has_inventory_noun = bool(tokens.intersection(_INVENTORY_TRIGGER_NOUNS) or raw_tokens.intersection(_INVENTORY_TRIGGER_NOUNS))
    has_count_trigger = bool(re.search(r"\b(how many|number of|count|total)\b", normalized))
    has_list_trigger = bool(re.search(r"\b(list|which|what are|show)\b", normalized))
    has_available_trigger = bool(re.search(r"\b(available|exist|there are|there is|do we have)\b", normalized))
    is_inventory = (
        (has_count_trigger and has_inventory_noun)
        or (has_list_trigger and has_inventory_noun and has_available_trigger)
        or (has_list_trigger and tokens.intersection({"project", "benefit", "policy", "setup"}))
        or (question_analysis.answer_type == "list" and has_inventory_noun and has_available_trigger)
    )
    if not is_inventory:
        return None

    target_tokens = tuple(
        token
        for token in tokens
        if token not in _INVENTORY_GENERIC_TERMS and token not in {"available", "many", "total"}
    )
    if not target_tokens and topic_scope:
        target_tokens = tuple(
            token
            for token in _content_tokens(" ".join([topic_scope.topic.name, *topic_scope.retrieval_terms]))
            if token not in _INVENTORY_GENERIC_TERMS
        )
    target_tokens = tuple(dict.fromkeys(target_tokens))
    section_inventory = "section" in raw_tokens and not tokens.intersection({"project", "benefit", "policy", "setup"})
    mode = "count" if has_count_trigger else "list"
    return InventoryRequestMatch(
        mode=mode,
        target_tokens=target_tokens,
        target_label=_target_label(target_tokens, section_inventory=section_inventory),
        section_inventory=section_inventory,
    )


def _allowed_inventory_documents(documents: list[SourceDocument], access_scope: AccessScope) -> list[SourceDocument]:
    allowed_acl_tags = set(access_scope.allowed_acl_tags)
    allowed: list[SourceDocument] = []
    for document in documents:
        if document.tenant_id != access_scope.tenant_id:
            continue
        if access_scope.source_filters and document.source_system not in access_scope.source_filters:
            continue
        document_acl_tags = set(document.acl_tags)
        if document_acl_tags and not document_acl_tags.intersection(allowed_acl_tags):
            continue
        allowed.append(document)
    return allowed


def _matching_inventory_documents(
    documents: list[SourceDocument],
    match: InventoryRequestMatch,
) -> list[SourceDocument]:
    if not match.target_tokens:
        return _dedupe_documents(documents)
    scored: list[tuple[int, str, SourceDocument]] = []
    target = set(match.target_tokens)
    required_overlap = 2 if len(target) > 1 else 1
    for document in documents:
        section_text = _document_section_text(document)
        title_text = document.title
        metadata_text = _document_metadata_text(document)
        tag_text = " ".join(document.tags)
        section_tokens = _content_tokens(section_text)
        title_tokens = _content_tokens(title_text)
        metadata_tokens = _content_tokens(metadata_text)
        tag_tokens = _content_tokens(tag_text)
        overlap = target.intersection(section_tokens | title_tokens | metadata_tokens | tag_tokens)
        phrase_score = _inventory_phrase_score(" ".join(match.target_tokens), section_text, title_text, metadata_text, tag_text)
        if len(overlap) < required_overlap and phrase_score <= 0:
            continue
        score = len(overlap)
        score += len(target.intersection(section_tokens)) * 3
        score += len(target.intersection(title_tokens)) * 2
        score += len(target.intersection(tag_tokens))
        score += phrase_score
        scored.append((score, f"{document.section_path or ''}/{document.title}".lower(), document))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return _dedupe_documents([document for _score, _sort_key, document in scored])


def _inventory_phrase_score(target_phrase: str, *values: str) -> int:
    if not target_phrase:
        return 0
    score = 0
    for index, value in enumerate(values):
        if _contains_phrase(value, target_phrase):
            score += 8 if index == 0 else 4
    return score


def _dedupe_documents(documents: list[SourceDocument]) -> list[SourceDocument]:
    deduped: dict[str, SourceDocument] = {}
    for document in documents:
        existing = deduped.get(document.source_item_id)
        if existing is None or document.last_modified_utc > existing.last_modified_utc:
            deduped[document.source_item_id] = document
    return sorted(deduped.values(), key=lambda document: ((document.section_path or "").lower(), document.title.lower()))


def _format_inventory_answer(match: InventoryRequestMatch, documents: list[SourceDocument]) -> str:
    if match.section_inventory:
        return _format_section_inventory_answer(documents)

    count = len(documents)
    noun = _inventory_noun(match.target_tokens, count=count)
    section_label = _common_section_label(documents)
    heading = match.target_label if match.target_label != "Pages" else "Available Pages"
    location = f" in {section_label}" if section_label and match.target_tokens else ""
    lead = f"There {'is' if count == 1 else 'are'} {count} accessible {noun}{location}."
    listed_documents = documents[:25]
    lines = [f"### {heading}", "", lead]
    if listed_documents:
        lines.extend(["", "Page titles:"])
        lines.extend(f"- {document.title}" for document in listed_documents)
        if count > len(listed_documents):
            lines.append(f"- ...and {count - len(listed_documents)} more pages.")
    return "\n".join(lines)


def _format_section_inventory_answer(documents: list[SourceDocument]) -> str:
    sections: dict[str, int] = {}
    for document in documents:
        section = _document_section_text(document) or "Unsectioned"
        sections[section] = sections.get(section, 0) + 1
    items = sorted(sections.items(), key=lambda item: item[0].lower())
    lines = ["### Available Sections", "", f"There {'is' if len(items) == 1 else 'are'} {len(items)} accessible sections."]
    if items:
        lines.extend(["", "Sections:"])
        lines.extend(f"- {section} ({count} {'page' if count == 1 else 'pages'})" for section, count in items[:25])
        if len(items) > 25:
            lines.append(f"- ...and {len(items) - 25} more sections.")
    return "\n".join(lines)


def _no_inventory_answer(match: InventoryRequestMatch) -> str:
    noun = _inventory_noun(match.target_tokens)
    return f"I could not find any accessible {noun} in the indexed OneNote source titles or sections."


def _inventory_response(
    *,
    answer: str,
    documents: list[SourceDocument],
    request: AnswerRequest,
    access_scope: AccessScope,
    candidate_count: int,
    started: float,
    suggested_questions: list[str],
) -> AnswerResponse:
    citations = [_citation_from_source_document(index, document) for index, document in enumerate(documents[:25], start=1)]
    duration_ms = int((time.perf_counter() - started) * 1000)
    retrieval_meta = RetrievalMetadata(
        strategy="metadata-inventory",
        access_scope=access_scope,
        requested_top_k=request.top_k,
        candidate_count=candidate_count,
        returned_count=len(documents),
        filtered_count=0,
        source_filters=access_scope.source_filters,
        collections_queried=[],
        payload_filter={},
        duration_ms=duration_ms,
        topic_id=request.topic_id,
        answer_type="inventory",
    )
    return AnswerResponse(
        answer=answer,
        citations=citations,
        retrieval_meta=retrieval_meta,
        metadata=AnswerMetadata(
            provider="metadata-inventory",
            model="source-title-index",
            retrieval_strategy="metadata-inventory",
            retrieved_chunk_count=len(citations),
            source_systems=sorted({document.source_system for document in documents}),
            duration_ms=duration_ms,
            retrieval_latency_ms=duration_ms,
            completion_latency_ms=0,
            freshness_delay_ms=_freshness_delay_ms(citations),
            citation_count=len(citations),
        ),
        suggested_questions=suggested_questions,
    )


def _citation_from_source_document(index: int, document: SourceDocument) -> Citation:
    return Citation(
        index=index,
        chunk_id=f"inventory:{document.source_item_id}",
        source_item_id=document.source_item_id,
        chunk_index=0,
        title=document.title,
        source_system=document.source_system,
        source_container=document.source_container,
        source_url=document.source_url,
        section_path=document.section_path,
        snippet=f"Page title: {document.title}. Section: {_document_section_text(document) or 'N/A'}.",
        last_modified_utc=document.last_modified_utc,
        last_edited_by=_metadata_string(
            document.metadata,
            "last_edited_by",
            "lastEditedBy",
            "last_modified_by",
            "lastModifiedBy",
        ),
        client_url=_metadata_string(document.metadata, "client_url", "oneNoteClientUrl", "onenote_client_url"),
        metadata={**document.metadata, "inventory_source": True},
    )


def _target_label(target_tokens: tuple[str, ...], *, section_inventory: bool) -> str:
    if section_inventory:
        return "Available Sections"
    if not target_tokens:
        return "Pages"
    if "project" in target_tokens:
        return "Projects"
    if "benefit" in target_tokens:
        return "Company Benefits"
    if "policy" in target_tokens:
        return "Company Policies"
    return " ".join(target_tokens).title()


def _inventory_noun(target_tokens: tuple[str, ...], *, count: int | None = None) -> str:
    if "project" in target_tokens:
        return "project" if count == 1 else "projects"
    if "benefit" in target_tokens:
        return "benefit page" if count == 1 else "benefit pages"
    if "policy" in target_tokens:
        return "policy page" if count == 1 else "policy pages"
    if "setup" in target_tokens:
        return "setup page" if count == 1 else "setup pages"
    if "guide" in target_tokens:
        return "guide page" if count == 1 else "guide pages"
    return "page" if count == 1 else "pages"


def _common_section_label(documents: list[SourceDocument]) -> str:
    sections = {_document_section_name(document) for document in documents}
    sections.discard("")
    return next(iter(sections)) if len(sections) == 1 else ""


def _document_section_text(document: SourceDocument) -> str:
    return document.section_path or str(document.metadata.get("section_name") or "").strip()


def _document_section_name(document: SourceDocument) -> str:
    metadata_section = str(document.metadata.get("section_name") or "").strip()
    if metadata_section:
        return metadata_section
    if document.section_path:
        return document.section_path.rsplit("/", maxsplit=1)[-1].strip()
    return ""


def _document_metadata_text(document: SourceDocument) -> str:
    values = [
        document.metadata.get("notebook_name"),
        document.metadata.get("section_name"),
        document.metadata.get("page_id"),
    ]
    return " ".join(str(value) for value in values if value)


def _final_answer_is_valid(
    answer_text: str,
    citations: list[Citation],
    evidence_assessment: EvidenceAssessment,
) -> bool:
    if _is_no_information_text(answer_text):
        return True
    if not citations:
        return False
    allowed_chunk_ids = {
        grade.chunk_id
        for grade in evidence_assessment.grades
        if grade.relevance == "direct" or (grade.relevance == "partial" and grade.answers_question)
    }
    if not allowed_chunk_ids:
        return False
    if any(citation.chunk_id not in allowed_chunk_ids for citation in citations):
        return False
    return True


def _merge_retrieval_results(
    question_analysis: QuestionAnalysis,
    results: list[RetrievalResult],
    *,
    top_k: int,
) -> RetrievalResult:
    if not results:
        raise ValueError("At least one retrieval result is required.")

    deduped: dict[str, object] = {}
    for result in results:
        for chunk in result.chunks:
            existing = deduped.get(chunk.chunk_id)
            if existing is None or chunk.score > existing.score:
                deduped[chunk.chunk_id] = chunk

    chunks = list(deduped.values())
    chunks.sort(
        key=lambda chunk: (
            -analysis_relevance_score(question_analysis, chunk),
            -chunk.score,
            chunk.title,
            chunk.chunk_index,
        )
    )
    primary = results[0].metadata
    metadata = RetrievalMetadata(
        strategy=f"{primary.strategy}+multi-query",
        access_scope=primary.access_scope,
        requested_top_k=top_k,
        candidate_count=sum(result.metadata.candidate_count for result in results),
        returned_count=min(len(chunks), top_k),
        filtered_count=sum(result.metadata.filtered_count for result in results),
        source_filters=primary.source_filters,
        collections_queried=sorted(
            {
                collection
                for result in results
                for collection in result.metadata.collections_queried
            }
        ),
        payload_filter=primary.payload_filter,
        query_count=len(question_analysis.search_queries),
        query_variants=list(question_analysis.search_queries),
        question_intent=question_analysis.main_intent,
        answer_type=question_analysis.required_answer_type,
        duration_ms=sum(result.metadata.duration_ms for result in results),
    )
    return RetrievalResult(chunks=chunks[:top_k], metadata=metadata)


def _request_with_topic_scope(request: AnswerRequest, topic_scope: AnswerTopicScope | None) -> AnswerRequest:
    if topic_scope is None:
        return request
    return request.model_copy(
        update={
            "user_context": topic_scope.user_context,
            "source_filters": topic_scope.source_filters,
        }
    )


def _topic_aware_query(query: str, topic_scope: AnswerTopicScope | None) -> str:
    if topic_scope is None or not topic_scope.retrieval_terms:
        return query
    values = [query, *topic_scope.retrieval_terms]
    return " ".join(dict.fromkeys(value.strip() for value in values if value.strip()))


def _prioritize_topic_chunks(chunks: list, topic_scope: AnswerTopicScope | None) -> list:
    if topic_scope is None or not topic_scope.retrieval_terms:
        return chunks

    topic_tokens = _content_tokens(" ".join(topic_scope.retrieval_terms))
    if not topic_tokens:
        return chunks

    prioritized = []
    for chunk in chunks:
        chunk_tokens = _content_tokens(
            " ".join([chunk.title, chunk.section_path or "", chunk.chunk_text, " ".join(chunk.tags)])
        )
        overlap = topic_tokens.intersection(chunk_tokens)
        if overlap:
            prioritized.append(chunk.model_copy(update={"score": chunk.score + len(overlap)}))
        else:
            prioritized.append(chunk)
    return prioritized


def _context_budget_for_depth(answer_depth: str) -> int:
    if answer_depth == "concise":
        return 5000
    if answer_depth == "detailed":
        return 10000
    return 7000


_FENCE_BLOCK = re.compile(r"(```.*?```)", re.DOTALL)


def _strip_inline_citation_markers(answer_text: str) -> str:
    # Never edit inside fenced code blocks - punctuation/whitespace there is
    # part of commands (e.g. "wayland-0 ./build/...") and must be preserved.
    pieces = _FENCE_BLOCK.split(answer_text)
    for index, piece in enumerate(pieces):
        if index % 2 == 1:  # captured fenced block
            continue
        piece = re.sub(r"\s*\[\d+\](?=([.,;:!?])|\s|$)", "", piece)
        piece = re.sub(r"[ \t]+([.,;:!?])", r"\1", piece)
        piece = re.sub(r"[ \t]+\n", "\n", piece)
        pieces[index] = piece
    return "".join(pieces).strip()


def _strip_trailing_source_line(answer_text: str) -> str:
    lines = answer_text.rstrip().splitlines()
    if not lines:
        return answer_text.strip()
    if not re.match(r"(?i)^\s*[_*]?\s*sources?\s*:\s*.+?\s*[_*]?\s*$", lines[-1]):
        return answer_text.strip()
    lines = lines[:-1]
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip()


def _is_no_information_text(answer_text: str) -> bool:
    normalized = _normalized_words(answer_text)
    return normalized in {
        "no information",
        "i could not find that information in the available onenote notes",
    }


def _normalize_no_information_text(answer_text: str) -> str:
    if _is_no_information_text(answer_text):
        return NO_INFORMATION_ANSWER
    return answer_text


_STOP_WORDS = {
    "a",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "could",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "info",
    "information",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "should",
    "the",
    "there",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "about",
    "give",
    "tell",
    "whate",
    "whats",
    "based",
    "company",
    "following",
    "means",
    "note",
    "notes",
    "page",
    "provided",
    "says",
    "source",
    "states",
    "that",
    "this",
    "you",
    "your",
}


def _content_tokens(value: str) -> set[str]:
    return {
        _normalize_token(token)
        for token in re.findall(r"[^\W_]+", value.lower())
        if len(token) > 2 and token not in _STOP_WORDS
    }


def _normalize_token(token: str) -> str:
    if len(token) > 5 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def _chunk_relevance_score(question: str, chunk) -> float:
    question_tokens = _content_tokens(question)
    if not question_tokens:
        return 0.0
    if _is_value_reference_only(question, chunk.chunk_text):
        return 0.0

    title_tokens = _content_tokens(chunk.title)
    section_tokens = _content_tokens(chunk.section_path or "")
    body_tokens = _content_tokens(chunk.chunk_text)
    tag_tokens = _content_tokens(" ".join(chunk.tags))
    all_tokens = title_tokens | section_tokens | body_tokens | tag_tokens
    overlap = question_tokens.intersection(all_tokens)
    fuzzy_score = fuzzy_metadata_relevance_score(question, chunk)
    if not overlap and fuzzy_score <= 0:
        return 0.0

    score = float(len(overlap))
    score += (len(overlap) / len(question_tokens)) * 2.0
    score += len(question_tokens.intersection(title_tokens)) * 3.0
    score += len(question_tokens.intersection(section_tokens)) * 1.0
    score += fuzzy_score

    key_phrase = _question_key_phrase(question)
    if key_phrase:
        if _contains_phrase(chunk.title, key_phrase):
            score += 12.0
        if _contains_phrase(chunk.section_path or "", key_phrase):
            score += 4.0
        if _contains_phrase(chunk.chunk_text, key_phrase):
            score += 3.0
        if _line_with_phrase_has_label(chunk.chunk_text, key_phrase):
            score += 10.0

    if _is_value_question(question) and _value_signal_present(chunk.chunk_text):
        score += 4.0
    return score


def _question_key_phrase(question: str) -> str:
    canonical_phrase = canonical_key_phrase(question)
    if canonical_phrase:
        return canonical_phrase
    tokens = [token for token in re.findall(r"[^\W_]+", question.lower()) if token not in _STOP_WORDS]
    if len(tokens) < 2:
        return ""
    return " ".join(tokens[-4:])


def _contains_phrase(value: str, phrase: str) -> bool:
    if not phrase:
        return False
    normalized_value = _normalized_words(value)
    return any(variant in normalized_value for variant in _phrase_variants(phrase))


def _phrase_variants(phrase: str) -> list[str]:
    normalized_phrase = _normalized_words(phrase)
    tokens = normalized_phrase.split()
    if len(tokens) <= 2:
        return [normalized_phrase] if normalized_phrase else []
    variants = [normalized_phrase]
    for size in range(min(3, len(tokens)), 1, -1):
        suffix = " ".join(tokens[-size:])
        if suffix not in variants:
            variants.append(suffix)
        prefix = " ".join(tokens[:size])
        if prefix not in variants:
            variants.append(prefix)
    return variants


def _normalized_words(value: str) -> str:
    return " ".join(_normalize_token(token) for token in re.findall(r"[^\W_]+", value.lower()))


def _line_with_phrase_has_label(value: str, phrase: str) -> bool:
    for line in value.splitlines():
        if _contains_phrase(line, phrase) and ":" in line:
            return True
    return False


def _is_value_question(question: str) -> bool:
    normalized = _normalized_words(question)
    return bool(
        "work hour" in normalized
        or "office hour" in normalized
        or "what time" in normalized
        or "what hour" in normalized
        or re.search(r"\b(when|how many|how much)\b", normalized)
    )


def _value_signal_present(value: str) -> bool:
    return bool(
        re.search(r"\b\d{1,2}:\d{2}\b", value)
        or re.search(r"\b\d{1,2}(st|nd|rd|th)\b", value, flags=re.IGNORECASE)
        or re.search(r"\b\d{1,2}\s*[-–]?\s*[^\W_\d]{1,4}\b", value, flags=re.IGNORECASE)
        or re.search(r"\b\d+\s*(hours?|days?|minutes?)\b", value, flags=re.IGNORECASE)
        or re.search(r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b", value, flags=re.IGNORECASE)
    )


def _is_value_reference_only(question: str, value: str) -> bool:
    if not _is_value_question(question):
        return False
    key_phrase = _question_key_phrase(question)
    if not key_phrase or not _contains_phrase(value, key_phrase):
        return False
    return not _value_signal_present(value)


def _answer_lacks_expected_value(question: str, answer_text: str, chunks: list) -> bool:
    if not _is_value_question(question):
        return False
    context_has_value = any(_chunk_relevance_score(question, chunk) > 0 and _value_signal_present(chunk.chunk_text) for chunk in chunks)
    return context_has_value and not _value_signal_present(answer_text)


def _answer_is_grounded_enough(question: str, answer_text: str, chunks: list) -> bool:
    answer_tokens = _content_tokens(re.sub(r"\[\d+\]", "", answer_text))
    if not answer_tokens:
        return False
    if not _answer_directly_addresses_question(question, answer_text):
        return False

    allowed_tokens = _content_tokens(question)
    for chunk in chunks:
        allowed_tokens.update(_content_tokens(chunk.title))
        allowed_tokens.update(_content_tokens(chunk.section_path or ""))
        allowed_tokens.update(_content_tokens(chunk.chunk_text))
        allowed_tokens.update(_content_tokens(" ".join(chunk.tags)))

    supported_tokens = answer_tokens.intersection(allowed_tokens)
    if not supported_tokens:
        return False
    support_ratio = len(supported_tokens) / len(answer_tokens)
    return support_ratio >= 0.65 and not _has_material_unsupported_content(
        answer_tokens.difference(allowed_tokens),
        answer_tokens,
    )


def _answer_directly_addresses_question(question: str, answer_text: str) -> bool:
    question_tokens = _content_tokens(question)
    if not question_tokens:
        return True
    answer_tokens = _content_tokens(re.sub(r"\[\d+\]", "", answer_text))
    if not answer_tokens:
        return False
    if _is_value_question(question) and _value_signal_present(answer_text):
        return True
    overlap = question_tokens.intersection(answer_tokens)
    return bool(overlap) and (len(overlap) / len(question_tokens)) >= 0.4


def _answer_matches_current_question(question_analysis: QuestionAnalysis, answer_text: str, chunks: list) -> bool:
    answer_body = _answer_without_source_lines(answer_text)
    if _missing_context_backed_focus_token(question_analysis, answer_body, chunks):
        return False
    if _answer_directly_addresses_question(question_analysis.original_question, answer_body):
        return True
    if _is_value_question(question_analysis.search_text) and _value_signal_present(answer_body):
        return True

    normalized_answer = _normalized_words(answer_body)
    for entity in question_analysis.important_entities:
        normalized_entity = _normalized_words(entity)
        if normalized_entity in _GENERIC_ENTITY_TERMS:
            continue
        if len(normalized_entity) > 2 and normalized_entity in normalized_answer:
            return True

    intent_topic = canonical_key_phrase(question_analysis.search_text)
    if intent_topic and intent_topic in normalized_answer:
        return True

    answer_tokens = _content_tokens(answer_body)
    if not answer_tokens:
        return False

    entity_tokens = _content_tokens(" ".join(question_analysis.important_entities))
    if entity_tokens:
        entity_overlap = answer_tokens.intersection(entity_tokens)
        if entity_overlap and len(entity_overlap) / len(entity_tokens) >= 0.4:
            return True

    semantic_tokens = _content_tokens(" ".join([*question_analysis.synonyms, *question_analysis.paraphrases]))
    semantic_overlap = answer_tokens.intersection(semantic_tokens)
    if question_analysis.required_answer_type == "yes_no" and semantic_overlap.intersection(
        {"allowed", "approval", "approved", "requires", "require", "policy"}
    ):
        return True
    return bool(semantic_overlap) and len(semantic_overlap) / max(len(semantic_tokens), 1) >= 0.25


def _missing_context_backed_focus_token(question_analysis: QuestionAnalysis, answer_text: str, chunks: list) -> bool:
    if question_analysis.specificity != "specific_fact":
        return False
    focus_tokens = _specific_focus_tokens(question_analysis)
    if not focus_tokens:
        return False

    context_tokens = _chunk_collection_tokens(chunks)
    required_tokens = focus_tokens.intersection(context_tokens)
    if not required_tokens:
        return False

    answer_tokens = _content_tokens(answer_text)
    return not bool(required_tokens.intersection(answer_tokens))


def _has_context_backed_specific_focus(question_analysis: QuestionAnalysis, chunks: list) -> bool:
    if question_analysis.specificity != "specific_fact":
        return False
    focus_tokens = _specific_focus_tokens(question_analysis)
    if not focus_tokens:
        return False
    return bool(focus_tokens.intersection(_chunk_collection_tokens(chunks)))


def _chunk_collection_tokens(chunks: list) -> set[str]:
    return _content_tokens(
        " ".join(
            " ".join([chunk.title, chunk.section_path or "", chunk.chunk_text, " ".join(chunk.tags)])
            for chunk in chunks
        )
    )


def _specific_focus_tokens(question_analysis: QuestionAnalysis) -> set[str]:
    tokens = _content_tokens(question_analysis.original_question)
    canonical_tokens = _content_tokens(canonical_key_phrase(question_analysis.search_text))
    generic_tokens = {_normalize_token(term) for term in _GENERIC_ENTITY_TERMS}
    focus_tokens = tokens.difference(generic_tokens)

    if len(focus_tokens.difference(canonical_tokens)) >= 1:
        return focus_tokens.difference(canonical_tokens)
    return focus_tokens


def _answer_without_source_lines(answer_text: str) -> str:
    return re.sub(r"(?im)^_?sources?:.*$", "", answer_text).strip()


def _answer_covers_selected_context(question: str, answer_text: str, chunks: list) -> bool:
    selected_citations = [
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
            last_modified_utc=chunk.last_modified_utc,
        )
        for index, chunk in enumerate(chunks, start=1)
    ]
    fallback_citations = _select_fallback_citations(question, chunks, selected_citations)
    if not fallback_citations:
        return True
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    selected_tokens: set[str] = set()
    for citation in fallback_citations[:1]:
        chunk = chunks_by_id.get(citation.chunk_id)
        if chunk is None:
            continue
        for segment in _best_supported_segments(question, chunk):
            selected_tokens.update(_content_tokens(segment))
    if not selected_tokens:
        return True
    answer_tokens = _content_tokens(re.sub(r"\[\d+\]", "", answer_text))
    coverage = len(answer_tokens.intersection(selected_tokens)) / len(selected_tokens)
    return coverage >= 0.6


def _answer_is_too_narrow_for_structured_question(question: str, answer_text: str, chunks: list) -> bool:
    if not _is_value_question(question):
        return False
    context_value_lines: list[str] = []
    for chunk in chunks:
        if _chunk_relevance_score(question, chunk) <= 0:
            continue
        context_value_lines.extend(
            line for line in _best_supported_segments(question, chunk) if _value_signal_present(line)
        )
    if len(context_value_lines) <= 1:
        return False
    answer_value_lines = [line for line in re.split(r"\n+|(?<=[.!?])\s+", answer_text) if _value_signal_present(line)]
    return len(answer_value_lines) < min(2, len(context_value_lines))


def _has_material_unsupported_content(unsupported_tokens: set[str], answer_tokens: set[str]) -> bool:
    if not unsupported_tokens:
        return False
    if len(unsupported_tokens) <= 2 and len(unsupported_tokens) / max(len(answer_tokens), 1) <= 0.25:
        return False
    return True


def _append_missing_citation(answer_text: str, citations: list[Citation]) -> str:
    if not citations or re.search(r"\[\d+\]", answer_text):
        return answer_text
    citation_marker = f"[{citations[0].index}]"
    stripped = answer_text.rstrip()
    if not stripped:
        return answer_text
    if stripped.endswith((".", "!", "?")):
        return f"{stripped} {citation_marker}"
    return f"{stripped} {citation_marker}"


_HEDGE_RELEVANCE_ORDER = {"direct": 3, "partial": 2, "related": 1, "irrelevant": 0}


def _related_chunks_for_hedge(
    question_analysis: QuestionAnalysis,
    grades: tuple[EvidenceGrade, ...],
    chunks: list,
    *,
    limit: int = 3,
) -> list:
    """Pick the chunks worth surfacing behind a "partially related" caveat.

    Keeps only chunks that grading did not mark irrelevant and that share a real
    topical link with the question (see ``_chunk_supports_hedge``), ranked by how
    relevant grading judged them. Returns an empty list when nothing qualifies.
    """
    grade_by_id = {grade.chunk_id: grade for grade in grades}
    scored: list[tuple[int, float, object]] = []
    for chunk in chunks:
        grade = grade_by_id.get(chunk.chunk_id)
        if grade is None or grade.relevance == "irrelevant":
            continue
        if not _chunk_supports_hedge(question_analysis, chunk):
            continue
        scored.append((_HEDGE_RELEVANCE_ORDER.get(grade.relevance, 0), grade.confidence, chunk))
    scored.sort(key=lambda item: (-item[0], -item[1]))
    return [chunk for _relevance, _confidence, chunk in scored[:limit]]


def _chunk_supports_hedge(question_analysis: QuestionAnalysis, chunk) -> bool:
    """True when a chunk is genuinely topically related to the question.

    Requires more than one weak/generic shared word so a coincidental overlap
    (for example "paid" between a salary question and a paid-leave note) never
    surfaces a misleading near-answer.
    """
    if _is_value_reference_only(question_analysis.search_text, chunk.chunk_text):
        return False
    haystack = _content_tokens(
        " ".join([chunk.title, chunk.section_path or "", chunk.chunk_text, " ".join(chunk.tags)])
    )
    if not haystack:
        return False
    must_tokens = _content_tokens(" ".join(question_analysis.must_have_concepts))
    if _meaningful_tokens(must_tokens.intersection(haystack)):
        return True
    entity_tokens = _content_tokens(" ".join(question_analysis.important_entities))
    if len(_meaningful_tokens(entity_tokens.intersection(haystack))) >= 2:
        return True
    query_tokens = _content_tokens(question_analysis.search_text)
    return len(_meaningful_tokens(query_tokens.intersection(haystack))) >= 2


def _meaningful_tokens(tokens: set[str]) -> set[str]:
    return {token for token in tokens if token not in _GENERIC_HEDGE_TERMS}


def _hedged_answer_text(body: str) -> str:
    return f"{HEDGED_ANSWER_PREAMBLE}\n\n{body.strip()}"


def _extractive_response(
    question_analysis: QuestionAnalysis | str,
    chunks: list,
    citations: list[Citation],
) -> tuple[str, list[Citation]]:
    if isinstance(question_analysis, QuestionAnalysis):
        selection_question = question_analysis.search_text
        extraction_question = (
            question_analysis.original_question
            if _has_context_backed_specific_focus(question_analysis, chunks)
            else " ".join(question_analysis.semantic_queries)
            if question_analysis.semantic_queries
            else question_analysis.search_text
            if canonical_key_phrase(question_analysis.search_text)
            else question_analysis.original_question
        )
    else:
        selection_question = question_analysis
        extraction_question = question_analysis
    if isinstance(question_analysis, QuestionAnalysis) and is_procedure_question(question_analysis):
        procedure = _procedure_extractive_answer(chunks, citations)
        if procedure is not None:
            return procedure
    selected_citations = _select_fallback_citations(selection_question, chunks, citations)
    answer = _extractive_answer(extraction_question, chunks, selected_citations)
    if _is_no_information_text(answer):
        return NO_INFORMATION_ANSWER, []
    return answer, selected_citations


_PROCEDURE_FALLBACK_KINDS = {
    "procedure",
    "prerequisites",
    "install",
    "configuration",
    "commands",
    "run",
    "verification",
    "checklist",
    "troubleshooting",
}


def _procedure_extractive_answer(
    chunks: list,
    citations: list[Citation],
) -> tuple[str, list[Citation]] | None:
    """Build a full, multi-section setup answer from procedure chunks.

    Only uses content already present in the retrieved chunks. Returns ``None``
    when no procedure content is available so the caller can fall back to the
    standard extractive path.
    """
    procedure_chunks = [chunk for chunk in chunks if chunk_kind_of(chunk) in _PROCEDURE_FALLBACK_KINDS]
    if not procedure_chunks:
        return None
    procedure_chunks.sort(key=lambda chunk: (0 if chunk_kind_of(chunk) == "procedure" else 1, -chunk.score))
    citations_by_chunk = {citation.chunk_id: citation for citation in citations}

    sections: list[str] = []
    used_citations: list[Citation] = []
    seen_headings: set[str] = set()
    title = procedure_chunks[0].title
    for chunk in procedure_chunks:
        rendered = _render_procedure_markdown(chunk.chunk_text, seen_headings)
        if not rendered:
            continue
        sections.append(rendered)
        citation = citations_by_chunk.get(chunk.chunk_id)
        if citation is not None and citation not in used_citations:
            used_citations.append(citation)
        if chunk_kind_of(chunk) == "procedure":
            break  # the combined chunk already covers the whole procedure

    body = "\n\n".join(part for part in sections if part).strip()
    if not body:
        return None
    heading_title = title if re.search(r"\bsetup\b", title, re.IGNORECASE) else f"{title} setup"
    answer = f"### {heading_title}\n\n{body}"
    return answer, (used_citations or citations[:1])


def _render_procedure_markdown(text: str, seen_headings: set[str]) -> str:
    """Reformat clean procedure text into nested Markdown for an answer.

    Drops the page title and metadata lines, demotes section headings so they
    nest under the answer heading, and keeps fenced code blocks, lists, and
    table rows intact.
    """
    out: list[str] = []
    in_fence = False
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            out.append(line)
            in_fence = not in_fence
            continue
        if in_fence:
            out.append(line)
            continue
        if re.match(r"^#\s+\S", stripped):  # page H1 title - drop
            continue
        if _METADATA_FALLBACK_LABEL.match(stripped) or _is_breadcrumb_line(stripped):
            continue
        heading_match = re.match(r"^(#{2,6})\s+(.*)$", stripped)
        if heading_match:
            heading_text = heading_match.group(2).strip()
            key = heading_text.lower()
            if key in seen_headings:
                continue
            seen_headings.add(key)
            level = min(len(heading_match.group(1)) + 2, 6)
            out.append(f"{'#' * level} {heading_text}")
            continue
        out.append(line)
    # collapse excess blank lines
    rendered = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    return rendered


_METADATA_FALLBACK_LABEL = re.compile(
    r"^(section|repository|owner|author|summary|tags?|status|page metadata|last edited|last modified|notebook)\s*:",
    re.IGNORECASE,
)


def _is_breadcrumb_line(value: str) -> bool:
    return " / " in value or bool(re.search(r"\S\s-\s\d+\s\S", value))


def _select_fallback_citations(question: str, chunks: list, citations: list[Citation]) -> list[Citation]:
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    ranked: list[tuple[float, Citation]] = []
    value_question = _is_value_question(question)
    value_backed: list[tuple[float, Citation]] = []
    for citation in citations:
        chunk = chunks_by_id.get(citation.chunk_id)
        if chunk is None:
            continue
        if _is_value_reference_only(question, chunk.chunk_text):
            continue
        score = _chunk_relevance_score(question, chunk)
        if score <= 0:
            continue
        item = (score, citation)
        ranked.append(item)
        if value_question and _value_signal_present(chunk.chunk_text):
            value_backed.append(item)

    candidates = value_backed or ranked
    if not candidates:
        return citations[:1]
    candidates.sort(key=lambda item: (-item[0], item[1].index))
    limit = 2 if value_question else 3
    return [citation for _score, citation in candidates[:limit]]


def _extractive_answer(question: str, chunks: list, citations: list[Citation]) -> str:
    if not citations:
        return NO_INFORMATION_ANSWER
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    blocks = []
    for citation in citations[:3]:
        chunk = chunks_by_id.get(citation.chunk_id)
        lines = _best_supported_segments(question, chunk) if chunk is not None else [citation.snippet.strip()]
        title = _best_supported_heading(question, chunk, citation.title) if chunk is not None else citation.title
        block = _format_markdown_block(title, lines, citation.index, question=question)
        if not block:
            continue
        blocks.append(block)
    if not blocks:
        return NO_INFORMATION_ANSWER
    answer = "\n\n".join(blocks)
    # A chunk whose only usable text echoes its own title or heading is not a
    # real answer - decline rather than emit a title-only response.
    if _is_title_only_answer(answer, chunks):
        return NO_INFORMATION_ANSWER
    return answer


def _split_content_segments(value: str) -> list[tuple[str, bool]]:
    segments: list[tuple[str, bool]] = []
    for part, is_code in _iter_fence_aware_parts(value):
        if is_code:
            segments.append((part, False))  # fenced code block, kept atomic
            continue
        for raw_segment in re.split(r"(?<=[.!?])\s+|\n+", part):
            cleaned = raw_segment.strip(" \t\r\n-*")
            if not cleaned:
                continue
            is_page_heading = _is_page_heading(cleaned)
            is_heading = cleaned.startswith("#") or is_page_heading
            if is_heading:
                cleaned = cleaned.lstrip("#").strip()
            if is_page_heading:
                cleaned = _page_heading_text(cleaned)
            if cleaned:
                segments.append((cleaned, is_heading))
    return segments


def _iter_fence_aware_parts(value: str):
    """Yield (text, is_code) parts, keeping ```...``` fenced blocks atomic."""
    lines = value.replace("\r\n", "\n").split("\n")
    buffer: list[str] = []
    code: list[str] | None = None
    for line in lines:
        if line.strip().startswith("```"):
            if code is None:
                if buffer:
                    yield "\n".join(buffer), False
                    buffer = []
                code = [line]
            else:
                code.append(line)
                yield "\n".join(code), True
                code = None
            continue
        if code is not None:
            code.append(line)
        else:
            buffer.append(line)
    if code is not None:  # unterminated fence; treat as code
        yield "\n".join(code), True
    elif buffer:
        yield "\n".join(buffer), False


def _is_code_segment(value: str) -> bool:
    return value.lstrip().startswith("```")


def _strip_code_fence(value: str) -> str:
    lines = value.strip().split("\n")
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _is_page_heading(value: str) -> bool:
    return bool(re.match(r"^page\s*:", value, flags=re.IGNORECASE))


def _page_heading_text(value: str) -> str:
    return re.sub(r"^page\s*:\s*", "", value, flags=re.IGNORECASE).strip()


def _first_body_segment_index(segments: list[tuple[str, bool]]) -> int:
    for index, (_segment, is_heading) in enumerate(segments):
        if not is_heading:
            return index
    return 0


def _segment_window_segments(
    segments: list[tuple[str, bool]],
    start_index: int,
    *,
    include_following: bool,
) -> list[str]:
    if not segments:
        return []

    if start_index >= len(segments):
        start_index = len(segments) - 1
    if segments[start_index][1]:
        for index in range(start_index + 1, len(segments)):
            if not segments[index][1]:
                start_index = index
                break

    selected: list[str] = []
    max_segments = 6 if include_following else 3
    max_chars = 1200 if include_following else 900
    for segment, is_heading in segments[start_index:]:
        if is_heading:
            if selected:
                break
            continue
        selected.append(segment)
        if len(selected) >= max_segments or len(" ".join(selected)) >= max_chars:
            break

    if not selected:
        selected.append(segments[start_index][0])
    return selected


def _segment_window(segments: list[tuple[str, bool]], start_index: int) -> str:
    return "\n".join(_segment_window_segments(segments, start_index, include_following=True))


def _best_supported_segments(question: str, chunk) -> list[str]:
    question_tokens = _content_tokens(question)
    segments = _split_content_segments(chunk.chunk_text)
    if not segments:
        return [chunk.chunk_text.strip()] if chunk.chunk_text.strip() else []
    if not question_tokens:
        return _segment_window_segments(segments, 0, include_following=True)

    key_phrase = _question_key_phrase(question)
    if key_phrase:
        for index, (segment, is_heading) in enumerate(segments):
            if is_heading and _contains_phrase(segment, key_phrase):
                return _segment_window_segments(segments, index, include_following=True)
        if _topic_title_window_allowed(key_phrase) and (
            _contains_phrase(chunk.title, key_phrase) or _contains_phrase(chunk.section_path or "", key_phrase)
        ):
            return _segment_window_segments(segments, _first_body_segment_index(segments), include_following=True)

    if fuzzy_metadata_relevance_score(question, chunk) > 0:
        fuzzy_index = _best_fuzzy_metadata_segment_index(segments)
        return _segment_window_segments(segments, fuzzy_index, include_following=True)

    ranked: list[tuple[float, int]] = []
    title_tokens = _content_tokens(chunk.title)
    section_tokens = _content_tokens(chunk.section_path or "")
    for index, (segment, is_heading) in enumerate(segments):
        segment_tokens = _content_tokens(segment)
        overlap = question_tokens.intersection(segment_tokens)
        if not overlap:
            continue
        coverage = len(overlap) / len(question_tokens)
        title_overlap = question_tokens.intersection(title_tokens)
        section_overlap = question_tokens.intersection(section_tokens)
        informativeness = min(len(segment_tokens), 20) / 20
        heading_penalty = 2.0 if is_heading else 0.0
        score = (
            (len(overlap) * 2.0)
            + (coverage * 2.0)
            + (len(title_overlap) * 0.25)
            + (len(section_overlap) * 0.1)
            + informativeness
            - heading_penalty
        )
        intent_terms = {"focus", "objective", "purpose", "goal", "title", "name"}
        exact_intent_overlap = question_tokens.intersection(intent_terms).intersection(segment_tokens)
        score += len(exact_intent_overlap) * 6.0
        ranked.append((score, index))

    if not ranked:
        return _segment_window_segments(segments, _first_body_segment_index(segments), include_following=True)
    ranked.sort(key=lambda item: (-item[0], item[1]))
    start_index = ranked[0][1]
    include_following = bool(
        key_phrase
        and (
            _contains_phrase(chunk.title, key_phrase)
            or _contains_phrase(chunk.section_path or "", key_phrase)
            or (segments[start_index][1] and _contains_phrase(segments[start_index][0], key_phrase))
        )
    )
    return _segment_window_segments(segments, start_index, include_following=include_following)


def _best_fuzzy_metadata_segment_index(segments: list[tuple[str, bool]]) -> int:
    procedure_terms = {"install", "configure", "configuration", "run", "setup", "step", "verify", "verification"}
    first_informative = 0
    for index, (segment, is_heading) in enumerate(segments):
        if is_heading or _metadata_or_breadcrumb_segment(segment):
            continue
        if first_informative == 0:
            first_informative = index
        if _content_tokens(segment).intersection(procedure_terms):
            return index
    return first_informative


def _metadata_or_breadcrumb_segment(segment: str) -> bool:
    if _METADATA_FALLBACK_LABEL.match(segment) or _is_breadcrumb_line(segment):
        return True
    tokens = _content_tokens(segment)
    return bool(" - " in segment and len(tokens) <= 4 and not re.search(r"[.!?:]", segment))


def _best_supported_segment(question: str, chunk) -> str:
    return "\n".join(_best_supported_segments(question, chunk))


def _topic_title_window_allowed(key_phrase: str) -> bool:
    return canonical_key_phrase(key_phrase) == key_phrase


def _best_supported_heading(question: str, chunk, fallback_title: str) -> str:
    key_phrase = _question_key_phrase(question)
    if key_phrase:
        for segment, is_heading in _split_content_segments(chunk.chunk_text):
            if is_heading and _contains_phrase(segment, key_phrase):
                if _heading_is_subtitle_of_fallback(segment, fallback_title):
                    return fallback_title
                return segment
    return fallback_title


def _heading_is_subtitle_of_fallback(heading: str, fallback_title: str) -> bool:
    heading_tokens = _content_tokens(heading)
    fallback_tokens = _content_tokens(fallback_title)
    return bool(heading_tokens) and heading_tokens.issubset(fallback_tokens)


def _format_markdown_block(title: str, lines: list[str], citation_index: int, *, question: str) -> str:
    text_lines = [_clean_answer_line(line) for line in lines if not _is_code_segment(line)]
    text_lines = _filter_answer_lines(question, [line for line in text_lines if line])
    allowed_text = set(text_lines)

    parts: list[str] = []
    for line in lines:
        if _is_code_segment(line):
            code = _strip_code_fence(line)
            if code:
                parts.append(f"```{_code_lang(line)}\n{code}\n```")
            continue
        cleaned = _clean_answer_line(line)
        if not cleaned or cleaned not in allowed_text:
            continue
        bullet = _format_markdown_bullet(cleaned, citation_index)
        if bullet:
            parts.append(bullet)
    if not parts:
        return ""
    heading = title.strip() or "Answer"
    return f"### {heading}\n\n" + "\n".join(parts)


def _code_lang(fence_block: str) -> str:
    first_line = fence_block.lstrip().split("\n", 1)[0]
    return first_line.lstrip("`").strip() or "text"


def _clean_answer_line(value: str) -> str:
    cleaned = re.sub(r"\[\d+\]", "", value).strip(" \t\r\n-*")
    if cleaned.startswith("#"):
        cleaned = cleaned.lstrip("#").strip()
    return cleaned


def _format_markdown_bullet(value: str, citation_index: int) -> str:
    if not value:
        return ""
    if "|" in value and value.strip().startswith("|"):
        return value
    if ":" in value:
        label, body = value.split(":", 1)
        if label.strip() and body.strip():
            return f"- **{label.strip()}:** {body.strip().rstrip('.!?')}"
    return f"- {value.rstrip('.!?')}"


def _filter_answer_lines(question: str, lines: list[str]) -> list[str]:
    if not lines:
        return []
    if _is_value_question(question) and any(_value_signal_present(line) for line in lines):
        value_lines = [line for line in lines if _value_signal_present(line)]
        return value_lines or lines
    return lines


def _ensure_markdown_answer(answer_text: str, citations: list[Citation]) -> str:
    stripped = answer_text.strip()
    if not stripped or _is_no_information_text(stripped) or _looks_like_markdown(stripped):
        return stripped
    heading = citations[0].title if len(citations) == 1 and citations[0].title else "Answer"
    return f"### {heading}\n\n{stripped}"


def _looks_like_markdown(value: str) -> bool:
    stripped = value.lstrip()
    return (
        stripped.startswith("#")
        or stripped.startswith("- ")
        or stripped.startswith("* ")
        or stripped.startswith("|")
        or "\n- " in value
        or "\n|" in value
    )


def _is_title_only_answer(answer_text: str, chunks: list) -> bool:
    answer_tokens = _content_tokens(re.sub(r"\[\d+\]", "", answer_text))
    if not answer_tokens:
        return False

    title_or_section_tokens: set[str] = set()
    body_tokens: set[str] = set()
    for chunk in chunks:
        title_or_section_tokens.update(_content_tokens(chunk.title))
        title_or_section_tokens.update(_content_tokens(chunk.section_path or ""))
        title_or_section_tokens.update(_content_tokens(_heading_text(chunk.chunk_text)))
        body_tokens.update(_content_tokens(_body_text_without_headings(chunk.chunk_text)))

    return answer_tokens.issubset(title_or_section_tokens) and not answer_tokens.intersection(
        body_tokens.difference(title_or_section_tokens)
    )


def _body_text_without_headings(value: str) -> str:
    body_segments = [segment for segment, is_heading in _split_content_segments(value) if not is_heading]
    return " ".join(body_segments)


def _heading_text(value: str) -> str:
    heading_segments = [segment for segment, is_heading in _split_content_segments(value) if is_heading]
    return " ".join(heading_segments)


def _freshness_delay_ms(citations: list[Citation]) -> int | None:
    if not citations:
        return None
    newest_source_timestamp = max(citation.last_modified_utc.astimezone(UTC) for citation in citations)
    return max(0, int((datetime.now(UTC) - newest_source_timestamp).total_seconds() * 1000))


def _related_attachment_refs(question: str, chunk) -> list[dict]:
    refs = (chunk.metadata or {}).get("attachment_refs")
    if not isinstance(refs, list):
        return []
    return [
        ref
        for ref in refs
        if isinstance(ref, dict) and _attachment_related_to_chunk(question, chunk, ref)
    ]


def _attachment_refs(chunk) -> list[dict]:
    refs = (chunk.metadata or {}).get("attachment_refs")
    if not isinstance(refs, list):
        return []
    return [ref for ref in refs if isinstance(ref, dict)]


def _attachment_related_to_chunk(question: str, chunk, payload: dict) -> bool:
    file_name = str(payload.get("file_name") or "")
    download_url = str(payload.get("download_url") or "")
    if not file_name and not download_url:
        return False
    haystack = _normalized_words(" ".join([question, chunk.title, chunk.section_path or "", chunk.chunk_text]))
    name_words = _normalized_words(file_name)
    stem_words = _normalized_words(file_name.rsplit(".", maxsplit=1)[0])
    if name_words and name_words in haystack:
        return True
    if stem_words and stem_words in haystack:
        return True
    if download_url and download_url in chunk.chunk_text:
        return True
    tokens = _content_tokens(file_name)
    return bool(tokens and tokens.intersection(_content_tokens(question)))


def _download_from_metadata(metadata: dict) -> DownloadLink | None:
    download_id = metadata.get("download_id")
    file_name = metadata.get("attachment_file_name") or metadata.get("file_name")
    download_url = metadata.get("download_url")
    parent_source_item_id = metadata.get("parent_source_item_id")
    parent_title = metadata.get("parent_title")
    if not all([download_id, file_name, download_url, parent_source_item_id, parent_title]):
        return None
    return DownloadLink(
        download_id=str(download_id),
        file_name=str(file_name),
        mime_type=_optional_string(metadata.get("mime_type") or metadata.get("attachment_mime_type")),
        file_extension=str(metadata.get("attachment_file_extension") or metadata.get("file_extension") or ""),
        size_bytes=_int_value(metadata.get("attachment_size_bytes") or metadata.get("size_bytes")),
        readable=bool(metadata.get("readable", True)),
        parent_source_item_id=str(parent_source_item_id),
        parent_title=str(parent_title),
        download_url=str(download_url),
        indexed_source_item_id=_optional_string(metadata.get("indexed_source_item_id")),
    )


def _download_from_attachment(attachment: SourceAttachment) -> DownloadLink:
    return DownloadLink(
        download_id=attachment.download_id,
        file_name=attachment.file_name,
        mime_type=attachment.mime_type,
        file_extension=attachment.file_extension,
        size_bytes=attachment.size_bytes,
        readable=attachment.readable,
        parent_source_item_id=attachment.parent_source_item_id,
        parent_title=attachment.parent_title,
        download_url=f"/api/v1/attachments/{attachment.download_id}/download" if attachment.storage_path else attachment.resource_url,
        indexed_source_item_id=attachment.indexed_source_item_id,
    )


def _attachment_payload(attachment: SourceAttachment) -> dict:
    return {
        "download_id": attachment.download_id,
        "file_name": attachment.file_name,
        "download_url": f"/api/v1/attachments/{attachment.download_id}/download" if attachment.storage_path else attachment.resource_url,
        "parent_source_item_id": attachment.parent_source_item_id,
        "parent_title": attachment.parent_title,
        "file_extension": attachment.file_extension,
        "mime_type": attachment.mime_type,
        "size_bytes": attachment.size_bytes,
        "readable": attachment.readable,
        "indexed_source_item_id": attachment.indexed_source_item_id,
    }


def _append_downloads_section(answer_text: str, downloads: list[DownloadLink]) -> str:
    if not downloads or re.search(r"^###\s+Downloads\b", answer_text, flags=re.IGNORECASE | re.MULTILINE):
        return answer_text
    lines = ["### Downloads", ""]
    for download in downloads:
        label = "Readable source" if download.readable else "Download"
        detail = f"{label} from {download.parent_title}"
        lines.append(f"- [{download.file_name}]({download.download_url}) - {detail}")
    return f"{answer_text.rstrip()}\n\n" + "\n".join(lines)


def _optional_string(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_value(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _metadata_string(metadata: dict, *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, dict):
            value = value.get("displayName") or value.get("user", {}).get("displayName")
        if value:
            return str(value).strip()
    return None
