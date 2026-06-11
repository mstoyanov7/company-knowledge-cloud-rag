from typing import Any, Literal

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class AclBinding(BaseModel):
    binding_id: str
    principal_type: Literal["user", "group", "role", "tenant", "tag"] = "tag"
    principal_id: str
    acl_tag: str
    source: str = "normalized-metadata"


class UserContext(BaseModel):
    user_id: str = "local-user"
    email: str = "local@example.com"
    tenant_id: str = "local-tenant"
    acl_tags: list[str] = Field(default_factory=lambda: ["public"])
    groups: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)


class AccessScope(BaseModel):
    user_id: str
    email: str
    tenant_id: str
    allowed_acl_tags: list[str]
    groups: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    source_filters: list[str] = Field(default_factory=list)


class ChunkDocument(BaseModel):
    tenant_id: str
    source_system: str
    source_container: str
    source_item_id: str
    source_url: str
    title: str
    section_path: str | None = None
    last_modified_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    acl_tags: list[str] = Field(default_factory=list)
    acl_bindings: list[AclBinding] = Field(default_factory=list)
    content_hash: str
    chunk_id: str
    chunk_index: int
    chunk_text: str
    chunk_kind: str | None = None
    embedding_model: str
    language: str = "en"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float = 0.0


class SourceDocument(BaseModel):
    tenant_id: str
    source_system: str
    source_container: str
    source_item_id: str
    source_url: str
    title: str
    file_name: str
    file_extension: str
    mime_type: str | None = None
    section_path: str | None = None
    last_modified_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at_utc: datetime | None = None
    acl_tags: list[str] = Field(default_factory=list)
    acl_bindings: list[AclBinding] = Field(default_factory=list)
    content_hash: str
    content_text: str
    language: str = "en"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceAttachment(BaseModel):
    download_id: str
    tenant_id: str
    source_system: str
    source_container: str
    parent_source_item_id: str
    parent_title: str
    source_url: str
    resource_url: str
    file_name: str
    file_extension: str
    mime_type: str | None = None
    size_bytes: int = 0
    readable: bool = False
    indexed_source_item_id: str | None = None
    storage_path: str | None = None
    content_hash: str
    last_modified_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at_utc: datetime | None = None
    acl_tags: list[str] = Field(default_factory=list)
    acl_bindings: list[AclBinding] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DownloadLink(BaseModel):
    download_id: str
    file_name: str
    mime_type: str | None = None
    file_extension: str
    size_bytes: int = 0
    readable: bool = False
    parent_source_item_id: str
    parent_title: str
    download_url: str
    indexed_source_item_id: str | None = None


class NotebookPage(BaseModel):
    id: str
    title: str
    section_path: str | None = None
    source_url: str
    source_item_id: str
    source_system: str = "onenote"
    source_container: str | None = None
    last_modified_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at_utc: datetime | None = None
    snippet: str | None = None
    last_edited_by: str | None = None
    client_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NotebookSection(BaseModel):
    id: str
    title: str
    source_url: str | None = None
    section_path: str | None = None
    pages: list[NotebookPage] = Field(default_factory=list)


class Notebook(BaseModel):
    id: str
    title: str
    source_url: str | None = None
    sections: list[NotebookSection] = Field(default_factory=list)


class DocumentSummary(BaseModel):
    id: str
    title: str
    section_path: str | None = None
    source_url: str
    source_item_id: str
    source_system: str = "onenote"
    source_container: str | None = None
    last_modified_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at_utc: datetime | None = None
    snippet: str | None = None
    last_edited_by: str | None = None
    client_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentDetail(DocumentSummary):
    content_text: str


class RetrievalRequest(BaseModel):
    question: str
    user_context: UserContext = Field(default_factory=UserContext)
    top_k: int = 3
    source_filters: list[str] = Field(default_factory=list)
    section_filters: list[str] = Field(default_factory=list)
    access_scope: AccessScope | None = None
    topic_id: str | None = None
    topic_tags: list[str] = Field(default_factory=list)
    # Restrict retrieval to these OneNote pages (source_item_id) when the user
    # has picked one in answer to a clarifying question.
    focus_source_item_ids: list[str] = Field(default_factory=list)


class RetrievalMetadata(BaseModel):
    strategy: str
    access_scope: AccessScope
    requested_top_k: int
    candidate_count: int
    returned_count: int
    filtered_count: int
    source_filters: list[str] = Field(default_factory=list)
    section_filters: list[str] = Field(default_factory=list)
    collections_queried: list[str] = Field(default_factory=list)
    payload_filter: dict[str, Any] = Field(default_factory=dict)
    reranker: str | None = None
    query_count: int = 1
    query_variants: list[str] = Field(default_factory=list)
    question_intent: str | None = None
    answer_type: str | None = None
    evidence_sufficiency: str | None = None
    relevance_grades: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: int = 0
    topic_id: str | None = None
    topic_tags: list[str] = Field(default_factory=list)


class RetrievalResult(BaseModel):
    chunks: list[ChunkDocument]
    metadata: RetrievalMetadata
