import time
from contextlib import nullcontext
from datetime import UTC, datetime
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
        audit_logger: SecurityAuditLogger | None = None,
    ) -> None:
        self.llm = llm
        self.prompt_builder = prompt_builder
        self.retriever = retriever
        self.access_scope_resolver = access_scope_resolver
        self.reranker = reranker
        self.retrieval_candidate_multiplier = max(1, retrieval_candidate_multiplier)
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
                retrieval_result.metadata.returned_count = len(chunks)
            citations = self._build_citations(chunks)
            self._audit_retrieval(request, retrieval_result, citations)
            prompt = self.prompt_builder.build(request.question, chunks, citations)
            completion_started = time.perf_counter()
            generation = await self.llm.generate(prompt)
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
                answer=generation.answer_text,
                citations=citations,
                retrieval_meta=retrieval_result.metadata,
                metadata=AnswerMetadata(
                    provider=generation.provider,
                    model=generation.model,
                    retrieval_strategy=retrieval_result.metadata.strategy,
                    retrieved_chunk_count=len(chunks),
                    source_systems=sorted({chunk.source_system for chunk in chunks}),
                    duration_ms=duration_ms,
                    retrieval_latency_ms=retrieval_result.metadata.duration_ms,
                    completion_latency_ms=completion_latency_ms,
                    freshness_delay_ms=freshness_delay_ms,
                    citation_count=len(citations),
                ),
            )

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


def _freshness_delay_ms(citations: list[Citation]) -> int | None:
    if not citations:
        return None
    newest_source_timestamp = max(citation.last_modified_utc.astimezone(UTC) for citation in citations)
    return max(0, int((datetime.now(UTC) - newest_source_timestamp).total_seconds() * 1000))
