# Codex Prompt - Phase 5 Operations and Evaluation

Goal:
Make the system measurable, resilient, and ready for diploma evaluation.

Tasks:
- add retry policies for connector jobs
- add dead-letter storage for failed items
- add sync metrics:
  - items scanned
  - items changed
  - items skipped
  - indexing latency
  - retrieval latency
  - answer latency
- add structured tracing ids through ingestion and query flow
- add benchmark scripts for:
  - indexing throughput
  - retrieval latency
  - answer latency
- add an evaluation dataset format
- add a script that runs queries against a known test corpus and records:
  - citation correctness
  - top-k retrieval hit rate
  - freshness indicators
- add concise operator documentation

Definition of done:
- system failures are observable
- benchmark results can be exported
- diploma experiment results can be reproduced
