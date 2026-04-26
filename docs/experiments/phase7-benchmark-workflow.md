# Phase 7 Benchmark Workflow

## Goal

Measure whether the Cloud-RAG onboarding backend can answer cited questions with acceptable latency, throughput, freshness, and failure rate under realistic chat traffic.

## Experiment Variables

| Variable | Values |
|---|---|
| Retrieval provider | `mock`, `qdrant` |
| Dataset | `benchmarks/datasets/onboarding_questions.json` |
| User profile | employee, engineer, unauthorized employee |
| Test type | smoke, stress, spike, soak, distributed concurrent users |
| Observability | OpenTelemetry disabled, OpenTelemetry enabled |

## Metrics

| Metric | Source | Notes |
|---|---|---|
| p50/p95/p99 HTTP latency | k6/Locust | End-to-end API request latency |
| Throughput | k6/Locust | Requests per second |
| Failure rate | k6/Locust | HTTP failures plus invalid response failures |
| Retrieval latency | backend response metadata and OTel metric | Time spent in retriever |
| Completion latency | backend response metadata and OTel metric | Time spent in LLM adapter |
| Freshness delay | backend response metadata and OTel metric | Time since newest cited source modification |
| Citation count | backend response metadata and OTel metric | Number of citations returned |

## Procedure

1. Start the local stack with the desired `.env`.
2. Enable OpenTelemetry if this run should be traceable.
3. Confirm `/health` and `/ready` return success.
4. Run `benchmarks/k6/smoke.js`.
5. If smoke passes, run stress, spike, and soak tests.
6. Run Locust for distributed concurrent chat-user behavior.
7. Save raw outputs under `benchmarks/results/<run-id>/`.
8. Fill `benchmarks/results/templates/benchmark-summary.md`.
9. Record any operational anomalies, retries, or dead letters.
10. Use the result tables in the thesis experiment chapter.

## Acceptance Gates

| Gate | Target |
|---|---|
| Smoke failure rate | `< 1%` |
| Stress failure rate | `< 2%` |
| Spike failure rate | `< 5%` |
| p95 local mock response | `< 1500 ms` |
| p99 stress response | `< 5000 ms` |
| Unauthorized content leakage | `0 cases` |

These are prototype targets. Production targets should be recalibrated with the real vector store, real LLM provider, real tenant data, and realistic network placement.
