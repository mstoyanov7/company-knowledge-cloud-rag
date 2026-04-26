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
    acl_tags: list[str] = Field(default_factory=list)
    acl_bindings: list[AclBinding] = Field(default_factory=list)
    content_hash: str
    content_text: str
    language: str = "en"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalRequest(BaseModel):
    question: str
    user_context: UserContext = Field(default_factory=UserContext)
    top_k: int = 3
    source_filters: list[str] = Field(default_factory=list)
    access_scope: AccessScope | None = None


class RetrievalMetadata(BaseModel):
    strategy: str
    access_scope: AccessScope
    requested_top_k: int
    candidate_count: int
    returned_count: int
    filtered_count: int
    source_filters: list[str] = Field(default_factory=list)
    collections_queried: list[str] = Field(default_factory=list)
    payload_filter: dict[str, Any] = Field(default_factory=dict)
    reranker: str | None = None
    duration_ms: int = 0


class RetrievalResult(BaseModel):
    chunks: list[ChunkDocument]
    metadata: RetrievalMetadata
