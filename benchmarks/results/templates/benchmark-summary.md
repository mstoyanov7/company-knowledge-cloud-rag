# Benchmark Summary

Run ID: `<run-id>`  
Date: `<YYYY-MM-DD>`  
Git commit: `<commit-sha>`  
Environment: `<local/docker/cloud>`  
Dataset: `benchmarks/datasets/onboarding_questions.json`  
Backend mode: `<mock|qdrant>`  
OpenTelemetry endpoint: `<otlp-endpoint-or-none>`

| Scenario | Tool | Users/VUs | Duration | Requests | Throughput req/s | Failure Rate | HTTP p50 ms | HTTP p95 ms | HTTP p99 ms | Answer p95 ms | Retrieval p95 ms | Completion p95 ms | Freshness p95 ms | Avg Citations |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Smoke | k6 | 1 | 10 iters | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Stress | k6 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Spike | k6 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Soak | k6 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Concurrent Chat | Locust | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

## Observations

- Bottleneck:
- Error pattern:
- Retrieval latency behavior:
- Completion latency behavior:
- Freshness behavior:
- Citation behavior:

## Decision

- Accept / reject benchmark run:
- Required follow-up:
