import time
from contextlib import nullcontext
from datetime import UTC, datetime
import re
from textwrap import shorten

from rag_api.ports import LlmPort, RerankerPort, RetrievalPort
from rag_api.services.access_scope import AccessScopeResolver
from rag_api.services.prompt_builder import PromptBuilder
from rag_api.services.security_audit import SecurityAuditLogger
from shared_schemas import AnswerMetadata, AnswerRequest, AnswerResponse, Citation, RetrievalRequest

try:
    from opentelemetry import metrics, trace
except ModuleNotFoundError:  # pragma: no cover - optional runtime dependency
    metrics = None
    trace = None


class AnswerService:
    def __init__(
        self,
        *,
        llm: LlmPort,
        prompt_builder: PromptBuilder,
        retriever: RetrievalPort,
        access_scope_resolver: AccessScopeResolver,
        reranker: RerankerPort | None = None,
        retrieval_candidate_multiplier: int = 3,
        min_keyword_overlap: int = 1,
        audit_logger: SecurityAuditLogger | None = None,
    ) -> None:
        self.llm = llm
        self.prompt_builder = prompt_builder
        self.retriever = retriever
        self.access_scope_resolver = access_scope_resolver
        self.reranker = reranker
        self.retrieval_candidate_multiplier = max(1, retrieval_candidate_multiplier)
        self.min_keyword_overlap = max(0, min_keyword_overlap)
        self.audit_logger = audit_logger
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
            access_scope = self.access_scope_resolver.resolve(request.user_context, request.source_filters)
            candidate_top_k = request.top_k
            if self.reranker:
                candidate_top_k = max(request.top_k, request.top_k * self.retrieval_candidate_multiplier)
            retrieval_request = RetrievalRequest(
                question=request.question,
                user_context=request.user_context,
                top_k=candidate_top_k,
                source_filters=request.source_filters,
                access_scope=access_scope,
            )
            retrieval_result = await self.retriever.retrieve(retrieval_request)
            chunks = retrieval_result.chunks
            if self.reranker:
                chunks = self.reranker.rerank(request.question, chunks, top_k=request.top_k)
                retrieval_result.metadata.reranker = self.reranker.name
                retrieval_result.metadata.requested_top_k = request.top_k
            chunks = self._filter_relevant_chunks(request.question, chunks)
            retrieval_result.metadata.returned_count = len(chunks)
            citations = self._build_citations(chunks)
            self._audit_retrieval(request, retrieval_result, citations)
            prompt = self.prompt_builder.build(request.question, chunks, citations)
            completion_started = time.perf_counter()
            generation = await self.llm.generate(prompt)
            answer_text, citations = self._guard_generated_answer(
                question=request.question,
                answer_text=generation.answer_text,
                chunks=chunks,
                citations=citations,
            )
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
            )

    def _filter_relevant_chunks(self, question: str, chunks: list) -> list:
        if self.min_keyword_overlap <= 0:
            return chunks
        question_tokens = _content_tokens(question)
        if not question_tokens:
            return []
        relevant = []
        for chunk in chunks:
            if _is_value_reference_only(question, chunk.chunk_text):
                continue
            relevance_score = _chunk_relevance_score(question, chunk)
            overlap_count = int(relevance_score)
            if overlap_count >= self.min_keyword_overlap:
                relevant.append((relevance_score, chunk))
        relevant.sort(key=lambda item: (-item[0], -item[1].score, item[1].title, item[1].chunk_index))
        return [chunk for _relevance_score, chunk in relevant]

    def _guard_generated_answer(
        self,
        *,
        question: str,
        answer_text: str,
        chunks: list,
        citations: list[Citation],
    ) -> tuple[str, list[Citation]]:
        normalized_answer = answer_text.strip()
        if normalized_answer == "No information":
            if citations:
                return _extractive_response(question, chunks, citations)
            return "No information", []
        if not citations:
            return "No information", []

        cited_indexes = {int(index) for index in re.findall(r"\[(\d+)\]", normalized_answer)}
        valid_indexes = {citation.index for citation in citations}
        used_indexes = cited_indexes.intersection(valid_indexes)
        if not used_indexes:
            if _answer_is_grounded_enough(question, normalized_answer, chunks) and _answer_covers_selected_context(
                question,
                normalized_answer,
                chunks,
            ):
                selected_citations = _select_fallback_citations(question, chunks, citations)
                return _ensure_markdown_answer(
                    _append_missing_citation(normalized_answer, selected_citations),
                    selected_citations,
                ), selected_citations
            return _extractive_response(question, chunks, citations)

        chunks_by_index = {index: chunk for index, chunk in enumerate(chunks, start=1)}
        cited_chunks = [chunks_by_index[index] for index in sorted(used_indexes) if index in chunks_by_index]
        if _is_title_only_answer(normalized_answer, cited_chunks):
            return _extractive_response(question, chunks, citations)
        if not _answer_directly_addresses_question(question, normalized_answer):
            return _extractive_response(question, chunks, citations)

        allowed_tokens = _content_tokens(question)
        for chunk in cited_chunks:
            allowed_tokens.update(_content_tokens(chunk.title))
            allowed_tokens.update(_content_tokens(chunk.section_path or ""))
            allowed_tokens.update(_content_tokens(chunk.chunk_text))
            allowed_tokens.update(_content_tokens(" ".join(chunk.tags)))

        answer_tokens = _content_tokens(re.sub(r"\[\d+\]", "", normalized_answer))
        unsupported_tokens = answer_tokens.difference(allowed_tokens)
        if _has_material_unsupported_content(unsupported_tokens, answer_tokens):
            return _extractive_response(question, chunks, citations)
        if _answer_lacks_expected_value(question, normalized_answer, chunks):
            return _extractive_response(question, chunks, citations)
        if _answer_is_too_narrow_for_structured_question(question, normalized_answer, cited_chunks):
            return _extractive_response(question, chunks, citations)

        used_citations = [citation for citation in citations if citation.index in used_indexes]
        return _ensure_markdown_answer(normalized_answer, used_citations), used_citations

    def _build_citations(self, chunks: list) -> list[Citation]:
        citations: list[Citation] = []
        for index, chunk in enumerate(chunks, start=1):
            citations.append(
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
                    snippet=shorten(chunk.chunk_text, width=180, placeholder="..."),
                    last_modified_utc=chunk.last_modified_utc,
                    metadata={
                        "content_hash": chunk.content_hash,
                        "score": chunk.score,
                        "tags": chunk.tags,
                    },
                )
            )
        return citations

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


_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
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
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in _STOP_WORDS
    }


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
    if not overlap:
        return 0.0

    score = float(len(overlap))
    score += (len(overlap) / len(question_tokens)) * 2.0
    score += len(question_tokens.intersection(title_tokens)) * 3.0
    score += len(question_tokens.intersection(section_tokens)) * 1.0

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
    tokens = [token for token in re.findall(r"[a-z0-9]+", question.lower()) if token not in _STOP_WORDS]
    if len(tokens) < 2:
        return ""
    return " ".join(tokens[-4:])


def _contains_phrase(value: str, phrase: str) -> bool:
    if not phrase:
        return False
    return phrase in _normalized_words(value)


def _normalized_words(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _line_with_phrase_has_label(value: str, phrase: str) -> bool:
    normalized_phrase = _normalized_words(phrase)
    for line in value.splitlines():
        normalized_line = _normalized_words(line)
        if normalized_phrase in normalized_line and ":" in line:
            return True
    return False


def _is_value_question(question: str) -> bool:
    normalized = _normalized_words(question)
    return bool(
        "working hours" in normalized
        or "office hours" in normalized
        or "what time" in normalized
        or "what hours" in normalized
        or re.search(r"\b(when|how many|how much)\b", normalized)
    )


def _value_signal_present(value: str) -> bool:
    return bool(
        re.search(r"\b\d{1,2}:\d{2}\b", value)
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


def _extractive_response(question: str, chunks: list, citations: list[Citation]) -> tuple[str, list[Citation]]:
    selected_citations = _select_fallback_citations(question, chunks, citations)
    return _extractive_answer(question, chunks, selected_citations), selected_citations


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
    limit = 1 if value_question else 3
    return [citation for _score, citation in candidates[:limit]]


def _extractive_answer(question: str, chunks: list, citations: list[Citation]) -> str:
    if not citations:
        return "No information"
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
    return "\n\n".join(blocks) if blocks else "No information"


def _split_content_segments(value: str) -> list[tuple[str, bool]]:
    segments: list[tuple[str, bool]] = []
    for raw_segment in re.split(r"(?<=[.!?])\s+|\n+", value):
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
    max_segments = 5 if include_following else 1
    max_chars = 900 if include_following else 450
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
        ranked.append((score, index))

    if not ranked:
        return _segment_window_segments(segments, _first_body_segment_index(segments), include_following=True)
    ranked.sort(key=lambda item: (-item[0], item[1]))
    start_index = ranked[0][1]
    key_phrase = _question_key_phrase(question)
    include_following = bool(
        key_phrase
        and (
            _contains_phrase(chunk.title, key_phrase)
            or _contains_phrase(chunk.section_path or "", key_phrase)
            or (segments[start_index][1] and _contains_phrase(segments[start_index][0], key_phrase))
        )
    )
    return _segment_window_segments(segments, start_index, include_following=include_following)


def _best_supported_segment(question: str, chunk) -> str:
    return "\n".join(_best_supported_segments(question, chunk))


def _best_supported_heading(question: str, chunk, fallback_title: str) -> str:
    key_phrase = _question_key_phrase(question)
    if key_phrase:
        for segment, is_heading in _split_content_segments(chunk.chunk_text):
            if is_heading and _contains_phrase(segment, key_phrase):
                return segment
    return fallback_title


def _format_markdown_block(title: str, lines: list[str], citation_index: int, *, question: str) -> str:
    cleaned_lines = [_clean_answer_line(line) for line in lines]
    cleaned_lines = [line for line in cleaned_lines if line]
    cleaned_lines = _filter_answer_lines(question, cleaned_lines)
    if not cleaned_lines:
        return ""

    bullets = [_format_markdown_bullet(line, citation_index) for line in cleaned_lines]
    bullets = [bullet for bullet in bullets if bullet]
    if not bullets:
        return ""
    heading = title.strip() or "Answer"
    return f"### {heading}\n\n" + "\n".join(bullets)


def _clean_answer_line(value: str) -> str:
    cleaned = re.sub(r"\[\d+\]", "", value).strip(" \t\r\n-*")
    if cleaned.startswith("#"):
        cleaned = cleaned.lstrip("#").strip()
    return cleaned


def _format_markdown_bullet(value: str, citation_index: int) -> str:
    if not value:
        return ""
    if "|" in value and value.strip().startswith("|"):
        return f"{value} [{citation_index}]"
    if ":" in value:
        label, body = value.split(":", 1)
        if label.strip() and body.strip():
            return f"- **{label.strip()}:** {body.strip().rstrip('.!?')} [{citation_index}]"
    return f"- {value.rstrip('.!?')} [{citation_index}]"


def _filter_answer_lines(question: str, lines: list[str]) -> list[str]:
    if not lines:
        return []
    if _is_value_question(question) and any(_value_signal_present(line) for line in lines):
        value_lines = [line for line in lines if _value_signal_present(line)]
        return value_lines or lines
    return lines


def _ensure_markdown_answer(answer_text: str, citations: list[Citation]) -> str:
    stripped = answer_text.strip()
    if not stripped or stripped == "No information" or _looks_like_markdown(stripped):
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
