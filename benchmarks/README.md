# Performance Benchmarks

This directory contains Phase 7 benchmark assets for the chat API and retrieval pipeline.

## Prerequisites

- Running local stack: `docker compose up --build`
- `RAG_API_KEY` set if the backend requires it
- k6 installed locally or run through Docker
- Locust installed with `pip install -e ".[perf]"` for distributed user simulation

Enable OpenTelemetry before starting the stack if you want benchmark traces and metrics exported:

```powershell
$env:OTEL_ENABLED='true'
$env:OTEL_SERVICE_NAME='rag-api-benchmark'
$env:OTEL_EXPORTER_OTLP_ENDPOINT='http://localhost:4318'
docker compose up --build
```

Use `BENCHMARK_RUN_ID` to correlate k6/Locust runs with backend logs and traces.

## k6

Local k6:

```powershell
$env:BASE_URL='http://localhost:8080'
$env:RAG_API_KEY='cloudrag-rag-key'
$env:BENCHMARK_RUN_ID='smoke-local-001'
k6 run benchmarks/k6/smoke.js
k6 run benchmarks/k6/stress.js
k6 run benchmarks/k6/spike.js
k6 run benchmarks/k6/soak.js
```

Docker k6 on Windows:

```powershell
docker run --rm -i `
  -e BASE_URL=http://host.docker.internal:8080 `
  -e RAG_API_KEY=cloudrag-rag-key `
  -e BENCHMARK_RUN_ID=smoke-docker-001 `
  -v ${PWD}/benchmarks:/benchmarks `
  grafana/k6 run /benchmarks/k6/smoke.js
```

Each k6 script records:

- HTTP p50/p95/p99 via `http_req_duration`
- custom total answer latency via `rag_answer_latency_ms`
- retrieval latency via `rag_retrieval_latency_ms`
- completion latency via `rag_completion_latency_ms`
- freshness delay via `rag_freshness_delay_ms`
- citation count via `rag_citation_count`
- throughput via `http_reqs` and `rag_chat_requests_total`
- failure rate via `http_req_failed` and `rag_failure_rate`

## Locust

Run a single-process local scenario:

```powershell
pip install -e ".[perf]"
$env:DATASET_PATH='benchmarks/datasets/onboarding_questions.json'
$env:RAG_API_KEY='cloudrag-rag-key'
$env:BENCHMARK_RUN_ID='locust-local-001'
locust -f benchmarks/locust/locustfile.py --host http://localhost:8080
```

Distributed mode:

```powershell
locust -f benchmarks/locust/locustfile.py --master --host http://localhost:8080
locust -f benchmarks/locust/locustfile.py --worker
locust -f benchmarks/locust/locustfile.py --worker
```

## Dataset

`benchmarks/datasets/onboarding_questions.json` is intentionally small and deterministic. It includes:

- employee-accessible onboarding questions
- engineering-only questions
- an unauthorized engineering question for ACL-filtering load behavior

Use the same dataset for k6, Locust, and the evaluation harness when comparing latency and retrieval quality.
