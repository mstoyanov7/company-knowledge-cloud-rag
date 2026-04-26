# Evaluation

`eval/datasets/onboarding_eval.json` is the fixed Phase 6 onboarding benchmark.

Run it with the local mock retriever:

```powershell
$env:RETRIEVAL_PROVIDER='mock'
$env:SECURITY_AUDIT_ENABLED='false'
rag_evaluate --dataset eval/datasets/onboarding_eval.json --output eval/results/latest.json
```

Metrics recorded per run:

- retrieval hit rate
- document recall
- citation correctness
- groundedness by expected answer terms
- answer latency

Use `--record-db` when PostgreSQL is running to persist the report into
`evaluation_runs`.
