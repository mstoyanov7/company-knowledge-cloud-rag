from dataclasses import dataclass, field
from typing import Protocol

from shared_schemas import Citation, ChunkDocument, RetrievalRequest, RetrievalResult, SourceAttachment, SourceDocument


@dataclass(slots=True)
class PromptContext:
    system_instruction: str
    user_question: str
    context_blocks: list[str]
    citations: list[Citation]
    question_analysis: dict[str, object] | None = None
    source_titles: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GenerationResult:
    provider: str
    model: str
    answer_text: str


class RetrievalPort(Protocol):
    name: str

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        ...

    async def ready(self) -> bool:
        ...


class DocumentMetadataPort(Protocol):
    name: str

    def list_documents(self) -> list[SourceDocument]:
        ...

    def list_attachments(self, parent_source_item_ids: list[str] | None = None) -> list[SourceAttachment]:
        ...

    def get_attachment(self, download_id: str) -> SourceAttachment | None:
        ...


class LlmPort(Protocol):
    provider_name: str
    model_name: str

    async def generate(self, prompt: PromptContext) -> GenerationResult:
        ...

    async def ready(self) -> bool:
        ...

    async def list_models(self) -> list[str]:
        ...


class RerankerPort(Protocol):
    name: str

    def rerank(self, question: str, chunks: list[ChunkDocument], *, top_k: int) -> list[ChunkDocument]:
        ...
