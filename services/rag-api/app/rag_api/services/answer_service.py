import time
from textwrap import shorten

from rag_api.ports import LlmPort, RetrievalPort
from rag_api.services.prompt_builder import PromptBuilder
from shared_schemas import AnswerMetadata, AnswerRequest, AnswerResponse, Citation, RetrievalRequest


class AnswerService:
    def __init__(
        self,
        *,
        llm: LlmPort,
        prompt_builder: PromptBuilder,
        retriever: RetrievalPort,
    ) -> None:
        self.llm = llm
        self.prompt_builder = prompt_builder
        self.retriever = retriever

    async def answer(self, request: AnswerRequest) -> AnswerResponse:
        started = time.perf_counter()
        retrieval_request = RetrievalRequest(
            question=request.question,
            user_context=request.user_context,
            top_k=request.top_k,
            source_filters=request.source_filters,
        )
        chunks = await self.retriever.retrieve(retrieval_request)
        citations = self._build_citations(chunks)
        prompt = self.prompt_builder.build(request.question, chunks, citations)
        generation = await self.llm.generate(prompt)
        duration_ms = int((time.perf_counter() - started) * 1000)

        return AnswerResponse(
            answer=generation.answer_text,
            citations=citations,
            metadata=AnswerMetadata(
                provider=generation.provider,
                model=generation.model,
                retrieval_strategy=self.retriever.name,
                retrieved_chunk_count=len(chunks),
                source_systems=sorted({chunk.source_system for chunk in chunks}),
                duration_ms=duration_ms,
            ),
        )

    def _build_citations(self, chunks: list) -> list[Citation]:
        citations: list[Citation] = []
        for index, chunk in enumerate(chunks, start=1):
            citations.append(
                Citation(
                    index=index,
                    chunk_id=chunk.chunk_id,
                    title=chunk.title,
                    source_system=chunk.source_system,
                    source_url=chunk.source_url,
                    snippet=shorten(chunk.chunk_text, width=180, placeholder="..."),
                    last_modified_utc=chunk.last_modified_utc,
                )
            )
        return citations
