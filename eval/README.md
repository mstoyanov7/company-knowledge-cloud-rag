# Evaluation

There are two complementary harnesses:

1. **Answer-level harness** (`rag_evaluate`) — runs whole questions through the RAG
   answer service and scores retrieval + answer quality.
2. **Embedding A/B harness** (`rag_embedding_eval`) — compares embedding models on
   pure retrieval quality, isolated from the answer pipeline. This is the Phase 2
   experiment behind [`baseline-table.md`](baseline-table.md).

`eval/results/` is gitignored (ad-hoc runs); the curated, committed evidence lives
in [`baseline-table.md`](baseline-table.md).

## 1. Answer-level harness

`eval/datasets/onboarding_eval.json` is the fixed onboarding benchmark. Run it with
the local mock retriever:

```powershell
$env:RETRIEVAL_PROVIDER='mock'
$env:SECURITY_AUDIT_ENABLED='false'
rag_evaluate --dataset eval/datasets/onboarding_eval.json --output eval/results/latest.json
```

Metrics recorded per run:

- retrieval hit rate, document recall, citation correctness
- **MRR** and **nDCG@k** (rank quality)
- groundedness by expected answer terms
- answer latency

Use `--record-db` when PostgreSQL is running to persist the report into
`evaluation_runs`.

## 2. Embedding A/B harness

Compares embedding models over [`datasets/retrieval_eval.json`](datasets/retrieval_eval.json)
(labeled corpus + queries, including paraphrase queries that share little vocabulary
with the relevant document). The lexical `token-hash` baseline runs fully offline;
`ollama` needs the embedding backend reachable (`ollama pull nomic-embed-text`).

```bash
rag_embedding_eval --providers token-hash-v1,ollama --k 5
# writes eval/results/embedding_baseline.{md,json}; copy the figures into baseline-table.md
```

Metrics: recall@k, MRR, nDCG@k, hit@k — overall and broken down by query kind.
A provider that cannot be reached (e.g. Ollama down) is reported as skipped rather
than failing the run.
