"""Embedding A/B retrieval evaluation.

Compares embedding models on pure retrieval quality, isolated from the answer
pipeline: embed a labeled corpus and queries with each model, rank documents by
cosine similarity, and score recall@k / MRR / nDCG@k. The lexical ``token-hash``
baseline runs fully offline; ``ollama`` needs the embedding backend reachable.

This is the experiment behind the Phase 2 baseline table: it quantifies how much
real semantic embeddings beat the lexical fallback, especially on paraphrase
queries that share little vocabulary with the relevant document.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from shared_schemas.embeddings import Embedder

from rag_api.evaluation.metrics import hit_at_k, ndcg_at_k, recall_at_k, reciprocal_rank


@dataclass(frozen=True, slots=True)
class RetrievalDocument:
    id: str
    title: str
    text: str


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    query_id: str
    question: str
    relevant_ids: tuple[str, ...]
    kind: str = "keyword"


@dataclass(frozen=True, slots=True)
class ProviderEvalResult:
    provider: str
    model: str
    vector_size: int
    query_count: int
    mean_recall_at_k: float
    mean_reciprocal_rank: float
    mean_ndcg_at_k: float
    hit_rate_at_k: float
    by_kind: dict[str, dict[str, float]] = field(default_factory=dict)
    error: str | None = None


def load_retrieval_dataset(path: str | Path) -> tuple[list[RetrievalDocument], list[RetrievalQuery]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    documents = [
        RetrievalDocument(id=str(item["id"]), title=str(item.get("title", "")), text=str(item["text"]))
        for item in raw.get("documents", [])
    ]
    queries = [
        RetrievalQuery(
            query_id=str(item["query_id"]),
            question=str(item["question"]),
            relevant_ids=tuple(str(value) for value in item.get("relevant_ids", [])),
            kind=str(item.get("kind", "keyword")),
        )
        for item in raw.get("queries", [])
    ]
    return documents, queries


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def evaluate_provider(
    embedder: Embedder,
    documents: list[RetrievalDocument],
    queries: list[RetrievalQuery],
    *,
    provider: str,
    model: str,
    k: int = 5,
) -> ProviderEvalResult:
    """Embed corpus + queries, rank by cosine, and aggregate ranking metrics."""
    doc_vectors = embedder.embed_documents([f"{doc.title}. {doc.text}" for doc in documents])
    doc_ids = [doc.id for doc in documents]

    per_kind_rr: dict[str, list[float]] = defaultdict(list)
    per_kind_ndcg: dict[str, list[float]] = defaultdict(list)
    recalls: list[float] = []
    rrs: list[float] = []
    ndcgs: list[float] = []
    hits: list[float] = []

    for query in queries:
        query_vector = embedder.embed_query(query.question)
        scored = sorted(
            zip(doc_ids, doc_vectors, strict=True),
            key=lambda pair: _cosine(query_vector, pair[1]),
            reverse=True,
        )
        ranked_ids = [doc_id for doc_id, _vector in scored]
        rr = reciprocal_rank(ranked_ids, query.relevant_ids)
        ndcg = ndcg_at_k(ranked_ids, query.relevant_ids, k=k)
        recalls.append(recall_at_k(ranked_ids, query.relevant_ids, k=k))
        rrs.append(rr)
        ndcgs.append(ndcg)
        hits.append(1.0 if hit_at_k(ranked_ids, query.relevant_ids, k=k) else 0.0)
        per_kind_rr[query.kind].append(rr)
        per_kind_ndcg[query.kind].append(ndcg)

    by_kind = {
        kind: {
            "mean_reciprocal_rank": _mean(per_kind_rr[kind]),
            "mean_ndcg_at_k": _mean(per_kind_ndcg[kind]),
            "query_count": float(len(per_kind_rr[kind])),
        }
        for kind in sorted(per_kind_rr)
    }
    return ProviderEvalResult(
        provider=provider,
        model=model,
        vector_size=embedder.vector_size,
        query_count=len(queries),
        mean_recall_at_k=_mean(recalls),
        mean_reciprocal_rank=_mean(rrs),
        mean_ndcg_at_k=_mean(ndcgs),
        hit_rate_at_k=_mean(hits),
        by_kind=by_kind,
    )


def _bm25_tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if token]


def evaluate_bm25(
    documents: list[RetrievalDocument],
    queries: list[RetrievalQuery],
    *,
    k: int = 5,
) -> ProviderEvalResult:
    """True lexical BM25 baseline (Okapi BM25 via rank_bm25) over the same corpus.

    Provides a strong sparse-retrieval reference point for the embedding models,
    instead of comparing only against the project's own token-hash fallback.
    """
    from rank_bm25 import BM25Okapi

    corpus = [_bm25_tokenize(f"{doc.title}. {doc.text}") for doc in documents]
    doc_ids = [doc.id for doc in documents]
    bm25 = BM25Okapi(corpus)

    per_kind_rr: dict[str, list[float]] = defaultdict(list)
    per_kind_ndcg: dict[str, list[float]] = defaultdict(list)
    recalls: list[float] = []
    rrs: list[float] = []
    ndcgs: list[float] = []
    hits: list[float] = []

    for query in queries:
        scores = bm25.get_scores(_bm25_tokenize(query.question))
        ranked_ids = [doc_id for doc_id, _score in sorted(zip(doc_ids, scores, strict=True), key=lambda pair: pair[1], reverse=True)]
        rr = reciprocal_rank(ranked_ids, query.relevant_ids)
        ndcg = ndcg_at_k(ranked_ids, query.relevant_ids, k=k)
        recalls.append(recall_at_k(ranked_ids, query.relevant_ids, k=k))
        rrs.append(rr)
        ndcgs.append(ndcg)
        hits.append(1.0 if hit_at_k(ranked_ids, query.relevant_ids, k=k) else 0.0)
        per_kind_rr[query.kind].append(rr)
        per_kind_ndcg[query.kind].append(ndcg)

    by_kind = {
        kind: {
            "mean_reciprocal_rank": _mean(per_kind_rr[kind]),
            "mean_ndcg_at_k": _mean(per_kind_ndcg[kind]),
            "query_count": float(len(per_kind_rr[kind])),
        }
        for kind in sorted(per_kind_rr)
    }
    return ProviderEvalResult(
        provider="bm25",
        model="Okapi BM25",
        vector_size=0,
        query_count=len(queries),
        mean_recall_at_k=_mean(recalls),
        mean_reciprocal_rank=_mean(rrs),
        mean_ndcg_at_k=_mean(ndcgs),
        hit_rate_at_k=_mean(hits),
        by_kind=by_kind,
    )


def render_markdown_table(results: list[ProviderEvalResult], *, k: int, dataset_name: str) -> str:
    lines = [
        f"# Embedding Baseline — {dataset_name}",
        "",
        f"Retrieval quality by embedding model (k={k}). Higher is better.",
        "",
        "| Provider | Model | Dim | Recall@k | MRR | nDCG@k | Hit@k |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        if result.error:
            lines.append(f"| {result.provider} | {result.model} | — | _error_ | — | — | — |")
            continue
        lines.append(
            f"| {result.provider} | {result.model} | {result.vector_size} "
            f"| {result.mean_recall_at_k:.3f} | {result.mean_reciprocal_rank:.3f} "
            f"| {result.mean_ndcg_at_k:.3f} | {result.hit_rate_at_k:.3f} |"
        )

    kinds = sorted({kind for result in results if not result.error for kind in result.by_kind})
    if kinds:
        lines.extend(["", "## MRR by query kind", "", "| Provider | " + " | ".join(kinds) + " |", "| --- | " + " | ".join("---" for _ in kinds) + " |"])
        for result in results:
            if result.error:
                continue
            cells = [f"{result.by_kind.get(kind, {}).get('mean_reciprocal_rank', 0.0):.3f}" for kind in kinds]
            lines.append(f"| {result.provider} | " + " | ".join(cells) + " |")

    errors = [result for result in results if result.error]
    if errors:
        lines.extend(["", "## Skipped providers", ""])
        lines.extend(f"- **{result.provider}** ({result.model}): {result.error}" for result in errors)
    lines.append("")
    return "\n".join(lines)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
