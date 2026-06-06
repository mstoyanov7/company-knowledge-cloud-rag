"""Local debug CLI to trace the RAG pipeline for a single question.

Usage::

    RAG_DEBUG_ENABLED=true python -m rag_api.debug.trace_answer "how to setup flutter embedded hmi"

Outputs the query analysis, retrieved/reranked/selected chunks (with
``chunk_kind`` and scores), the final assembled context, and the answer. This
is a debug-only tool; it is gated behind ``RAG_DEBUG_ENABLED`` and is never
exposed through the normal UI.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

from shared_schemas import AnswerRequest, UserContext
from shared_schemas.config import AppSettings, get_settings

from rag_api.dependencies import get_document_metadata, get_llm, get_retriever, get_topic_service
from rag_api.services import AccessScopeResolver, AnswerService, PromptBuilder, QueryPlanner
from rag_api.services.reranker import KeywordOverlapReranker


class _DebugCapture(logging.Handler):
    """Captures the structured ``rag_debug`` events emitted by AnswerService."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return
        prefix = "rag_debug "
        if message.startswith(prefix):
            try:
                self.events.append(json.loads(message[len(prefix):]))
            except json.JSONDecodeError:  # pragma: no cover - defensive
                pass


def _build_service(settings: AppSettings) -> AnswerService:
    llm = get_llm(settings)
    reranker = KeywordOverlapReranker() if settings.rerank_enabled else None
    return AnswerService(
        llm=llm,
        prompt_builder=PromptBuilder(),
        retriever=get_retriever(settings),
        metadata=get_document_metadata(settings),
        access_scope_resolver=AccessScopeResolver(),
        reranker=reranker,
        retrieval_candidate_multiplier=settings.retrieval_candidate_multiplier,
        min_keyword_overlap=settings.retrieval_min_keyword_overlap,
        query_planner=QueryPlanner(llm=llm),
        topic_service=get_topic_service(settings),
        debug_enabled=True,
    )


async def trace_answer(
    question: str,
    *,
    topic_id: str | None = None,
    answer_depth: str = "detailed",
    acl_tags: list[str] | None = None,
    settings: AppSettings | None = None,
) -> dict:
    settings = settings or get_settings()
    capture = _DebugCapture()
    logger = logging.getLogger("rag_api.services.answer_service")
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(capture)
    try:
        service = _build_service(settings)
        request = AnswerRequest(
            question=question,
            topic_id=topic_id,
            answer_depth=answer_depth,
            user_context=UserContext(acl_tags=acl_tags or settings.auth_default_acl_tag_list or ["public"]),
            top_k=8,
        )
        response = await service.answer(request)
    finally:
        logger.removeHandler(capture)
        logger.setLevel(previous_level)

    events = {event.get("event"): event for event in capture.events}
    context_blocks = events.get("selected_context", {}).get("context_blocks", [])
    return {
        "question": question,
        "topic_id": topic_id,
        "answer_depth": answer_depth,
        "query_analysis": events.get("query_plan", {}).get("plan", {}),
        "retrieved_chunks": events.get("retrieved_chunks", {}).get("chunks", []),
        "reranked_chunks": events.get("reranked_chunks", {}).get("scores", []),
        "evidence_grades": events.get("evidence_grades", {}).get("grades", []),
        "selected_chunks": events.get("selected_context", {}).get("source_titles", []),
        "final_context": "\n\n---\n\n".join(context_blocks),
        "answer": response.answer,
        "citations": [
            {"index": citation.index, "title": citation.title, "section_path": citation.section_path}
            for citation in response.citations
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m rag_api.debug.trace_answer",
        description="Trace the RAG pipeline for a question (debug only).",
    )
    parser.add_argument("question")
    parser.add_argument("--topic-id", default=None)
    parser.add_argument("--answer-depth", default="detailed", choices=["concise", "normal", "detailed"])
    parser.add_argument("--acl-tag", action="append", dest="acl_tags", help="ACL tag to include (repeatable).")
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.rag_debug_enabled:
        print(json.dumps({"error": "RAG debug is disabled. Set RAG_DEBUG_ENABLED=true to use this tool."}))
        return 2

    result = asyncio.run(
        trace_answer(
            args.question,
            topic_id=args.topic_id,
            answer_depth=args.answer_depth,
            acl_tags=args.acl_tags,
            settings=settings,
        )
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
