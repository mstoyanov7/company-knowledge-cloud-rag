from rag_api.ports import PromptContext
from shared_schemas import Citation, ChunkDocument


class PromptBuilder:
    system_instruction = (
        "Answer only from the retrieved onboarding context. "
        "Keep citations in square brackets like [1]."
    )

    def build(self, question: str, chunks: list[ChunkDocument], citations: list[Citation]) -> PromptContext:
        context_blocks = [
            f"[{citation.index}] {chunk.title}: {chunk.chunk_text}"
            for citation, chunk in zip(citations, chunks, strict=False)
        ]
        return PromptContext(
            system_instruction=self.system_instruction,
            user_question=question,
            context_blocks=context_blocks,
            citations=citations,
        )
