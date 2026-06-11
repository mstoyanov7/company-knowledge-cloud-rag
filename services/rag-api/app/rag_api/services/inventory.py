"""Inventory questions: "how many pages / projects / benefits do we have",
"list the available setups", etc.

These are answered directly from indexed document metadata (titles, sections,
tags) rather than the vector/answer pipeline, so they live in their own module.
``answer_inventory_question`` is the entry point the answer service calls; it
returns ``None`` when the question is not an inventory request, letting the normal
flow continue.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from shared_schemas import (
    AccessScope,
    AnswerMetadata,
    AnswerRequest,
    AnswerResponse,
    Citation,
    RetrievalMetadata,
    SourceDocument,
)

from rag_api.ports import DocumentMetadataPort
from rag_api.services.answer_support import _freshness_delay_ms, _metadata_string
from rag_api.services.query_understanding import QuestionAnalysis
from rag_api.services.text_analysis import _contains_phrase, _content_tokens, _normalized_words
from rag_api.services.topic_service import AnswerTopicScope


@dataclass(frozen=True, slots=True)
class InventoryRequestMatch:
    mode: str
    target_tokens: tuple[str, ...]
    target_label: str
    section_inventory: bool = False


def answer_inventory_question(
    *,
    metadata: DocumentMetadataPort | None,
    request: AnswerRequest,
    question_analysis: QuestionAnalysis,
    topic_scope: AnswerTopicScope | None,
    access_scope: AccessScope,
    suggested_questions: list[str],
    started: float,
) -> AnswerResponse | None:
    """Answer an inventory question from metadata, or ``None`` if not one."""
    match = _inventory_request_match(question_analysis, topic_scope)
    if match is None or metadata is None:
        return None

    documents = _allowed_inventory_documents(metadata.list_documents(), access_scope)
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
