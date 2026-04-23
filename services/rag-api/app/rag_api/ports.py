from dataclasses import dataclass
from typing import Protocol

from shared_schemas import Citation, ChunkDocument, RetrievalRequest


@dataclass(slots=True)
class PromptContext:
    system_instruction: str
    user_question: str
    context_blocks: list[str]
    citations: list[Citation]


@dataclass(slots=True)
class GenerationResult:
    provider: str
    model: str
    answer_text: str


class RetrievalPort(Protocol):
    name: str

    async def retrieve(self, request: RetrievalRequest) -> list[ChunkDocument]:
        ...

    async def ready(self) -> bool:
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
