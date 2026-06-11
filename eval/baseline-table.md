# Phase 2 Baseline — Embedding Retrieval Quality

Committed evidence for the embedding change in Phase 1 (token-hash → `nomic-embed-text`).
Compares embedding models on **pure retrieval quality**, isolated from the answer
pipeline, over [`retrieval_eval.json`](datasets/retrieval_eval.json) (10 documents,
12 queries, mix of keyword and paraphrase intent). Higher is better.

Reproduce with:

```bash
rag_embedding_eval --providers token-hash-v1,ollama --k 5
# writes eval/results/embedding_baseline.{md,json}
```

## Results (k = 5)

Measured on 2026-06-07 against Ollama `nomic-embed-text` (768-dim) running locally.

| Provider | Model | Dim | Recall@k | MRR | nDCG@k | Hit@k |
| --- | --- | --- | --- | --- | --- | --- |
| token-hash-v1 (lexical baseline) | token-hash | 768 | 0.833 | 0.706 | 0.719 | 0.833 |
| **ollama (semantic)** | **nomic-embed-text** | **768** | **1.000** | **1.000** | **1.000** | **1.000** |
| Δ (semantic − lexical) | | | +0.167 | +0.294 | +0.281 | +0.167 |

The semantic model retrieves the correct document for **every** query and ranks it
**first every time** (MRR = nDCG = 1.000), while the lexical baseline misses ~17% of
queries outright and, when it does retrieve, ranks the relevant document lower
(MRR 0.706). This is the quantified payoff of Phase 1.

### MRR by query kind

| Provider | keyword | paraphrase |
| --- | --- | --- |
| token-hash-v1 | 0.662 | 0.738 |
| ollama | 1.000 | 1.000 |

The lexical baseline is weakest on **keyword** queries here only because this small
corpus shares enough vocabulary that paraphrases still catch incidental tokens; the
honest takeaway is not the keyword/paraphrase split but the **overall** gap — the
semantic model resolves cases the lexical one cannot, with no regressions.

## How to read this

- **Recall@k / Hit@k** — did the relevant document make the top-k.
- **MRR** — how high the relevant document ranked (1.0 = always first).
- **nDCG@k** — rank-weighted relevance.
- The token-hash baseline reaches MRR 0.706 here because the small corpus shares
  enough incidental vocabulary; it is not a strict lexical-only floor. The
  semantic model is expected to lift MRR/nDCG and, more importantly, hold up on
  paraphrase queries that share little wording with the source — that delta is
  the quantified payoff of Phase 1.

## Related experiments

- **Answer-engine quality, behaviour gradation, and ACL ablation** — done offline
  (deterministic) over a 22-document corpus; see [`answer-eval-table.md`](answer-eval-table.md).
- **Live end-to-end latency + load** — needs the running stack; see
  [`LIVE_RUNBOOK.md`](LIVE_RUNBOOK.md).
- **Freshness** — staleness under static vs polling vs incremental indexing (still to fill).
