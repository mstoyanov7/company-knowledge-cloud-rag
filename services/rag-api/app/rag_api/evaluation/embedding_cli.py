from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from shared_schemas import get_settings
from shared_schemas.embeddings import EmbeddingError, create_embedder

from rag_api.evaluation.embedding_eval import (
    ProviderEvalResult,
    evaluate_bm25,
    evaluate_provider,
    load_retrieval_dataset,
    render_markdown_table,
)


def run() -> None:
    parser = argparse.ArgumentParser(
        description="Compare embedding models on retrieval quality (recall@k, MRR, nDCG@k)."
    )
    parser.add_argument("--dataset", default="eval/datasets/retrieval_eval.json", help="Labeled retrieval dataset.")
    parser.add_argument(
        "--providers",
        default="bm25,token-hash-v1,ollama",
        help="Comma-separated providers to compare. 'bm25' is a true Okapi BM25 lexical baseline.",
    )
    parser.add_argument("--k", type=int, default=5, help="Cutoff for recall@k / nDCG@k / hit@k.")
    parser.add_argument("--output", default="eval/results/embedding_baseline.md", help="Markdown table output path.")
    parser.add_argument("--json-output", default="eval/results/embedding_baseline.json", help="Raw JSON output path.")
    args = parser.parse_args()

    base_settings = get_settings()
    documents, queries = load_retrieval_dataset(args.dataset)
    dataset_name = Path(args.dataset).stem
    providers = [provider.strip() for provider in args.providers.split(",") if provider.strip()]

    results: list[ProviderEvalResult] = []
    for provider in providers:
        if provider == "bm25":
            result = evaluate_bm25(documents, queries, k=args.k)
            results.append(result)
            _print_summary(result)
            continue
        settings = base_settings.model_copy(update={"default_embedding_provider": provider})
        model = settings.embedding_model_name if provider not in {"token-hash-v1", "token-hash"} else "token-hash"
        try:
            embedder = create_embedder(settings)
            result = evaluate_provider(
                embedder, documents, queries, provider=provider, model=model, k=args.k
            )
        except EmbeddingError as error:
            result = ProviderEvalResult(
                provider=provider,
                model=model,
                vector_size=0,
                query_count=len(queries),
                mean_recall_at_k=0.0,
                mean_reciprocal_rank=0.0,
                mean_ndcg_at_k=0.0,
                hit_rate_at_k=0.0,
                error=str(error),
            )
        results.append(result)
        _print_summary(result)

    table = render_markdown_table(results, k=args.k, dataset_name=dataset_name)
    _write(Path(args.output), table)
    _write(Path(args.json_output), json.dumps([asdict(result) for result in results], indent=2))
    print(f"\nWrote {args.output} and {args.json_output}")


def _print_summary(result: ProviderEvalResult) -> None:
    if result.error:
        print(f"[{result.provider}] skipped: {result.error}")
        return
    print(
        f"[{result.provider}] model={result.model} dim={result.vector_size} "
        f"recall@k={result.mean_recall_at_k:.3f} MRR={result.mean_reciprocal_rank:.3f} "
        f"nDCG@k={result.mean_ndcg_at_k:.3f} hit@k={result.hit_rate_at_k:.3f}"
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    run()
