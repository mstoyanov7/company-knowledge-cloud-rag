import hashlib
import re
import time
from datetime import UTC, datetime
from typing import Iterable

from shared_schemas import AccessScope, AppSettings, ChunkDocument, RetrievalMetadata, RetrievalRequest, RetrievalResult


def _hash_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _tokenize(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


class MockRetriever:
    name = "mock-keyword-overlap"

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._documents = self._build_corpus()

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
        )
        question_tokens = _tokenize(request.question)
        allowed_acl_tags = set(access_scope.allowed_acl_tags)
        source_filters = set(access_scope.source_filters)

        scored: list[ChunkDocument] = []
        filtered_count = 0
        for document in self._documents:
            if source_filters and document.source_system not in source_filters:
                filtered_count += 1
                continue

            document_acl_tags = set(document.acl_tags)
            is_allowed = bool(allowed_acl_tags.intersection(document_acl_tags))
            if not is_allowed:
                filtered_count += 1
                continue

            overlap = question_tokens.intersection(_tokenize(document.chunk_text))
            if not overlap:
                continue

            scored.append(document.model_copy(update={"score": float(len(overlap))}))

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
                collections_queried=["mock"],
                duration_ms=duration_ms,
                payload_filter={
                    "tenant_id": access_scope.tenant_id,
                    "acl_tags": access_scope.allowed_acl_tags,
                    "source_system": access_scope.source_filters,
                },
            ),
        )

    async def ready(self) -> bool:
        return True

    def _build_corpus(self) -> tuple[ChunkDocument, ...]:
        documents = (
            self._document(
                source_system="sharepoint",
                source_container="sites/onboarding",
                source_item_id="sp-001",
                source_url="https://contoso.sharepoint.com/sites/onboarding/day-1",
                title="Day 1 onboarding checklist",
                section_path="HR / First day",
                acl_tags=["public", "employees"],
                chunk_index=0,
                chunk_text=(
                    "On day one, new hires should connect to the VPN, finish payroll forms, "
                    "review the handbook, and confirm their laptop setup with IT."
                ),
                tags=["onboarding", "hr", "it"],
            ),
            self._document(
                source_system="onenote",
                source_container="notebooks/onboarding",
                source_item_id="on-001",
                source_url="https://contoso.sharepoint.com/notebooks/onboarding/benefits",
                title="Benefits orientation notes",
                section_path="People Ops / Benefits",
                acl_tags=["public", "employees"],
                chunk_index=0,
                chunk_text=(
                    "Benefits enrollment opens during the first week. Employees should pick "
                    "health coverage, review paid leave rules, and activate the wellness portal."
                ),
                tags=["benefits", "people-ops"],
            ),
            self._document(
                source_system="sharepoint",
                source_container="sites/engineering",
                source_item_id="sp-002",
                source_url="https://contoso.sharepoint.com/sites/engineering/remote-work",
                title="Engineering remote work guide",
                section_path="Engineering / Handbook",
                acl_tags=["engineering"],
                chunk_index=0,
                chunk_text=(
                    "Engineering teammates should request repository access, enroll in on-call "
                    "rotation training, and use the incident handbook for production support."
                ),
                tags=["engineering", "access", "operations"],
            ),
        )
        return documents

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
        )
