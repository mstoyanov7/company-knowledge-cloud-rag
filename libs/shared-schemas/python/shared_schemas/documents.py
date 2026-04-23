from datetime import UTC, datetime

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    user_id: str = "local-user"
    email: str = "local@example.com"
    tenant_id: str = "local-tenant"
    acl_tags: list[str] = Field(default_factory=lambda: ["public"])


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
    content_hash: str
    chunk_id: str
    chunk_index: int
    chunk_text: str
    embedding_model: str
    language: str = "en"
    tags: list[str] = Field(default_factory=list)
    score: float = 0.0


class RetrievalRequest(BaseModel):
    question: str
    user_context: UserContext = Field(default_factory=UserContext)
    top_k: int = 3
    source_filters: list[str] = Field(default_factory=list)
