from rag_api.ports import PromptContext
from shared_schemas import Citation, ChunkDocument
from rag_api.services.context_builder import AnswerContext, build_answer_context
from rag_api.services.query_understanding import QuestionAnalysis, analyze_question


class PromptBuilder:
    system_instruction = (
        "You are a OneNote-only retrieval assistant for company knowledge. "
        "Answer only from the retrieved context supplied by the backend. "
        "Do not use outside knowledge, assumptions, memory, or unsupported reasoning. "
        "You may interpret the user's wording using the provided internal question analysis, but do not reveal that analysis. "
        "Do not expose hidden reasoning or chain-of-thought. "
        "Use only chunks that directly answer the user's specific question. "
        "Ignore retrieved chunks that are unrelated, only loosely related, or only contain page titles/headings. "
        "Do not answer by copying only the first keyword-matching sentence. "
        "Use the retrieved content to create a clear, descriptive answer that explains the relevant details. "
        "If multiple retrieved chunks directly answer the question, combine them into one complete answer. "
        "Do not stop after the first sentence if the context contains more directly relevant information. "
        "Do not answer using only a title, heading, section name, or filename. "
        "Write in a polite, conversational style while staying concise. "
        "Format the answer as clean Markdown. "
        "Use a short heading for the topic and bullets or tables for structured facts. "
        "For key-value source lines, preserve the labels as bold bullet labels. "
        "Do not include numeric source markers such as [1], [2], or source IDs in the visible answer. "
        "Cite the answer by ending with a short Markdown italic Source or Sources line that lists the OneNote page titles used. "
        "If the retrieved context does not directly contain the answer, reply exactly: "
        "I could not find that information in the available OneNote notes."
    )

    def build(
        self,
        question: str,
        chunks: list[ChunkDocument],
        citations: list[Citation],
        *,
        question_analysis: QuestionAnalysis | None = None,
        answer_context: AnswerContext | None = None,
    ) -> PromptContext:
        analysis = question_analysis or analyze_question(question)
        context = answer_context or build_answer_context(analysis, chunks, citations)
        return PromptContext(
            system_instruction=self.system_instruction,
            user_question=question,
            context_blocks=list(context.context_blocks),
            citations=citations,
            question_analysis={
                "detected_language": analysis.detected_language,
                "answer_type": analysis.answer_type,
                "important_entities": list(analysis.important_entities),
                "key_phrases": list(analysis.key_phrases),
                "rewritten_question": analysis.rewritten_question,
                "semantic_queries": list(analysis.semantic_queries),
                "keyword_queries": list(analysis.keyword_queries),
                "must_have_concepts": list(analysis.must_have_concepts),
                "avoid_concepts": list(analysis.avoid_concepts),
                "expected_evidence_type": analysis.expected_evidence_type,
                "specificity": analysis.specificity,
            },
            source_titles=list(context.source_titles),
        )
