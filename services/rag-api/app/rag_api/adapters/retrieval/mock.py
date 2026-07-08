import hashlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from shared_schemas import AccessScope, AppSettings, ChunkDocument, RetrievalMetadata, RetrievalRequest, RetrievalResult

from rag_api.services.retrieval_ranking import fuzzy_metadata_relevance_score


def _hash_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _tokenize(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


class MockRetriever:
    name = "mock-keyword-overlap"

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._documents = self._build_corpus()
        self._bm25 = None
        self._bm25_index: dict[str, int] = {}
        if str(getattr(settings, "mock_lexical_scoring", "overlap")).lower() == "bm25":
            try:
                from rank_bm25 import BM25Okapi

                tokenized = [
                    sorted(
                        _tokenize(
                            " ".join(
                                [doc.title, doc.section_path or "", doc.chunk_text, " ".join(doc.tags)]
                            )
                        )
                    )
                    for doc in self._documents
                ]
                self._bm25 = BM25Okapi(tokenized)
                self._bm25_index = {doc.chunk_id: index for index, doc in enumerate(self._documents)}
                self.name = "mock-bm25"
            except ImportError:  # pragma: no cover - optional dependency
                self._bm25 = None

    @property
    def documents(self) -> tuple[ChunkDocument, ...]:
        return self._documents

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        started = time.perf_counter()
        access_scope = request.access_scope or AccessScope(
            user_id=request.user_context.user_id,
            email=request.user_context.email,
            tenant_id=request.user_context.tenant_id,
            allowed_acl_tags=request.user_context.acl_tags,
            groups=request.user_context.groups,
            roles=request.user_context.roles,
            source_filters=request.source_filters,
            is_admin=request.user_context.is_admin,
        )
        question_tokens = _tokenize(request.question)
        bm25_scores = (
            self._bm25.get_scores(sorted(question_tokens)) if self._bm25 is not None and question_tokens else None
        )
        allowed_acl_tags = set(access_scope.allowed_acl_tags)
        source_filters = set(access_scope.source_filters)
        section_filters = list(dict.fromkeys(value.strip() for value in request.section_filters if value.strip()))
        section_filter_set = set(section_filters)
        focus_ids = set(request.focus_source_item_ids)

        scored: list[ChunkDocument] = []
        filtered_count = 0
        for document in self._documents:
            if focus_ids:
                parent_id = (document.metadata or {}).get("parent_source_item_id")
                if document.source_item_id not in focus_ids and parent_id not in focus_ids:
                    filtered_count += 1
                    continue
            if source_filters and document.source_system not in source_filters:
                filtered_count += 1
                continue
            section_name = str((document.metadata or {}).get("section_name") or "")
            if section_filter_set and section_name not in section_filter_set:
                filtered_count += 1
                continue

            document_acl_tags = set(document.acl_tags)
            is_allowed = access_scope.is_admin or bool(allowed_acl_tags.intersection(document_acl_tags))
            if not is_allowed:
                filtered_count += 1
                continue

            document_text = " ".join(
                [
                    document.title,
                    document.section_path or "",
                    document.chunk_text,
                    " ".join(document.tags),
                ]
            )
            overlap = question_tokens.intersection(_tokenize(document_text))
            fuzzy_score = fuzzy_metadata_relevance_score(request.question, document)
            if not overlap and fuzzy_score <= 0:
                continue

            topic_overlap = set(request.topic_tags).intersection(set(document.tags))
            if bm25_scores is not None:
                lexical_score = float(bm25_scores[self._bm25_index[document.chunk_id]])
            else:
                lexical_score = float(len(overlap))
            scored.append(
                document.model_copy(update={"score": lexical_score + len(topic_overlap) + fuzzy_score})
            )

        scored.sort(key=lambda item: (-item.score, item.title, item.chunk_index))
        top_k = min(request.top_k, self.settings.mock_top_k)
        chunks = scored[:top_k]
        duration_ms = int((time.perf_counter() - started) * 1000)
        return RetrievalResult(
            chunks=chunks,
            metadata=RetrievalMetadata(
                strategy=self.name,
                access_scope=access_scope,
                requested_top_k=request.top_k,
                candidate_count=len(scored),
                returned_count=len(chunks),
                filtered_count=filtered_count,
                source_filters=access_scope.source_filters,
                section_filters=section_filters,
                collections_queried=["mock"],
                duration_ms=duration_ms,
                payload_filter={
                    "tenant_id": access_scope.tenant_id,
                    "acl_tags": access_scope.allowed_acl_tags,
                    "source_system": access_scope.source_filters,
                    "section_filters": section_filters,
                    "topic_id": request.topic_id,
                    "topic_tags": request.topic_tags,
                },
                topic_id=request.topic_id,
                topic_tags=request.topic_tags,
            ),
        )

    async def ready(self) -> bool:
        return True

    def _build_corpus(self) -> tuple[ChunkDocument, ...]:
        corpus_path = getattr(self.settings, "mock_corpus_path", "")
        if corpus_path:
            loaded = self._load_corpus_file(corpus_path)
            if loaded:
                return loaded
        documents = (
            self._document(
                source_system="onenote",
                source_container="notebooks/onboarding",
                source_item_id="on-001",
                source_url="onenote://notebooks/onboarding/day-1",
                title="Day 1 onboarding checklist",
                section_path="HR / First day",
                acl_tags=["public", "employees"],
                chunk_index=0,
                chunk_text=(
                    "On day one, new hires should connect to the VPN, finish payroll forms, "
                    "review the handbook, and confirm their laptop setup with IT."
                ),
                tags=["onboarding", "hr", "it"],
                metadata={
                    "notebook_id": "nb-onboarding",
                    "notebook_name": "Onboarding",
                    "section_id": "sec-first-day",
                    "section_name": "First day",
                    "page_id": "on-001",
                    "last_edited_by": "People Ops",
                    "client_url": "onenote:///notebooks/onboarding/day-1",
                },
            ),
            self._document(
                source_system="onenote",
                source_container="notebooks/onboarding",
                source_item_id="on-002",
                source_url="onenote://notebooks/onboarding/benefits",
                title="Benefits orientation notes",
                section_path="People Ops / Benefits",
                acl_tags=["public", "employees"],
                chunk_index=0,
                chunk_text=(
                    "Benefits enrollment opens during the first week. Employees should pick "
                    "health coverage, review paid leave rules, and activate the wellness portal."
                ),
                tags=["benefits", "people-ops"],
                metadata={
                    "notebook_id": "nb-onboarding",
                    "notebook_name": "Onboarding",
                    "section_id": "sec-benefits",
                    "section_name": "Benefits",
                    "page_id": "on-002",
                    "last_edited_by": "Benefits Team",
                    "client_url": "onenote:///notebooks/onboarding/benefits",
                },
            ),
            self._document(
                source_system="onenote",
                source_container="notebooks/engineering",
                source_item_id="on-003",
                source_url="onenote://notebooks/engineering/remote-work",
                title="Engineering remote work guide",
                section_path="Engineering / Handbook",
                acl_tags=["engineering"],
                chunk_index=0,
                chunk_text=(
                    "Engineering teammates should request repository access, enroll in on-call "
                    "rotation training, and use the incident handbook for production support."
                ),
                tags=["engineering", "access", "operations"],
                metadata={
                    "notebook_id": "nb-engineering",
                    "notebook_name": "Engineering",
                    "section_id": "sec-handbook",
                    "section_name": "Handbook",
                    "page_id": "on-003",
                    "last_edited_by": "Engineering Enablement",
                    "client_url": "onenote:///notebooks/engineering/remote-work",
                },
            ),
        )
        return documents

    def _load_corpus_file(self, corpus_path: str) -> tuple[ChunkDocument, ...]:
        """Load a richer evaluation corpus from JSON.

        Each entry carries the same fields as :meth:`_document`. Missing optional
        fields fall back to sensible defaults so the eval corpus stays compact.
        """
        path = Path(corpus_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = raw.get("documents", raw) if isinstance(raw, dict) else raw
        documents: list[ChunkDocument] = []
        for entry in entries:
            documents.append(
                self._document(
                    source_system=entry.get("source_system", "onenote"),
                    source_container=entry.get("source_container", ""),
                    source_item_id=entry["source_item_id"],
                    source_url=entry.get("source_url", f"onenote://{entry['source_item_id']}"),
                    title=entry["title"],
                    section_path=entry.get("section_path", ""),
                    acl_tags=entry.get("acl_tags", ["public"]),
                    chunk_index=entry.get("chunk_index", 0),
                    chunk_text=entry["chunk_text"],
                    tags=entry.get("tags", []),
                    metadata=entry.get("metadata"),
                )
            )
        return tuple(documents)

    def _document(
        self,
        *,
        source_system: str,
        source_container: str,
        source_item_id: str,
        source_url: str,
        title: str,
        section_path: str,
        acl_tags: Iterable[str],
        chunk_index: int,
        chunk_text: str,
        tags: Iterable[str],
        metadata: dict | None = None,
    ) -> ChunkDocument:
        return ChunkDocument(
            tenant_id="local-tenant",
            source_system=source_system,
            source_container=source_container,
            source_item_id=source_item_id,
            source_url=source_url,
            title=title,
            section_path=section_path,
            last_modified_utc=datetime(2026, 4, 23, tzinfo=UTC),
            acl_tags=list(acl_tags),
            content_hash=_hash_text(chunk_text),
            chunk_id=f"{source_item_id}-chunk-{chunk_index}",
            chunk_index=chunk_index,
            chunk_text=chunk_text,
            embedding_model=self.settings.default_embedding_provider,
            language="en",
            tags=list(tags),
            metadata=metadata or {},
        )
