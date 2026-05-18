from rag_api.ports import PromptContext
from shared_schemas import Citation, ChunkDocument


class PromptBuilder:
    system_instruction = (
        "You are a OneNote-only retrieval assistant for company knowledge. "
        "Answer only from the retrieved context supplied by the backend. "
        "Do not use outside knowledge, assumptions, memory, or unsupported reasoning. "
        "Use only chunks that directly answer the user's specific question. "
        "Ignore retrieved chunks that are unrelated, only loosely related, or only contain page titles/headings. "
        "Do not answer by copying only the first keyword-matching sentence. "
        "Use the retrieved content to create a clear, descriptive answer that explains the relevant details. "
        "If multiple retrieved chunks directly answer the question, combine them into one complete answer. "
        "Do not stop after the first sentence if the context contains more directly relevant information. "
        "Do not answer using only a title, heading, section name, or filename. "
        "Format the answer as clean Markdown. "
        "Use a short heading for the topic and bullets or tables for structured facts. "
        "For key-value source lines, preserve the labels as bold bullet labels. "
        "Do not add a separate sources section. "
        "Every factual claim must include citation markers in square brackets like [1]. "
        "If the retrieved context does not directly contain the answer, reply exactly: No information."
    )

    def build(self, question: str, chunks: list[ChunkDocument], citations: list[Citation]) -> PromptContext:
        context_blocks = [
            "\n".join(
                [
                    f"[{citation.index}]",
                    f"Title: {chunk.title}",
                    f"Section: {chunk.section_path or 'N/A'}",
                    "Content:",
                    chunk.chunk_text,
                ]
            )
            for citation, chunk in zip(citations, chunks, strict=False)
        ]
        return PromptContext(
            system_instruction=self.system_instruction,
            user_question=question,
            context_blocks=context_blocks,
            citations=citations,
        )
