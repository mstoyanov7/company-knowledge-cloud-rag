from __future__ import annotations

from shared_schemas import AppSettings
from shared_schemas.embeddings import create_embedder

from rag_api.evaluation.embedding_eval import (
    evaluate_provider,
    load_retrieval_dataset,
    render_markdown_table,
)

DATASET = "eval/datasets/retrieval_eval.json"


def _token_hash_result():
    settings = AppSettings(default_embedding_provider="token-hash-v1", embedding_vector_size=256)
    documents, queries = load_retrieval_dataset(DATASET)
    embedder = create_embedder(settings)
    return evaluate_provider(
        embedder, documents, queries, provider="token-hash-v1", model="token-hash", k=5
    )


def test_embedding_eval_runs_offline_with_token_hash() -> None:
    result = _token_hash_result()
    assert result.query_count == 12
    assert 0.0 <= result.mean_recall_at_k <= 1.0
    assert 0.0 <= result.mean_reciprocal_rank <= 1.0
    assert 0.0 <= result.mean_ndcg_at_k <= 1.0
    assert set(result.by_kind) == {"keyword", "paraphrase"}


def test_lexical_baseline_leaves_headroom() -> None:
    # The token-hash baseline ranks by shared vocabulary alone, so it does not
    # perfectly resolve every query - leaving measurable headroom that the
    # semantic model is expected to close in the committed baseline table. (We do
    # not assert keyword-vs-paraphrase ordering: bag-of-words still matches many
    # paraphrases through incidental shared tokens, which is exactly why the real
    # token-hash-vs-ollama comparison, not a hand-labelled split, is the evidence.)
    result = _token_hash_result()
    assert result.mean_reciprocal_rank < 1.0
    assert result.mean_ndcg_at_k < 1.0


def test_render_markdown_table_includes_providers() -> None:
    table = render_markdown_table([_token_hash_result()], k=5, dataset_name="retrieval_eval")
    assert "Embedding Baseline" in table
    assert "token-hash-v1" in table
    assert "MRR by query kind" in table
