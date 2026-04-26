from __future__ import annotations

import re

from shared_schemas import ChunkDocument


def _tokenize(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


class KeywordOverlapReranker:
    name = "keyword-overlap-reranker"

    def rerank(self, question: str, chunks: list[ChunkDocument], *, top_k: int) -> list[ChunkDocument]:
        question_tokens = _tokenize(question)
        ranked: list[ChunkDocument] = []
        for chunk in chunks:
            overlap = question_tokens.intersection(_tokenize(chunk.chunk_text))
            score = chunk.score + (len(overlap) * 0.1)
            ranked.append(chunk.model_copy(update={"score": score}))
        ranked.sort(key=lambda item: (-item.score, item.title, item.chunk_index))
        return ranked[:top_k]
