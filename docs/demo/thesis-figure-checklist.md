# Thesis Figure Checklist

Use these figures in the diploma text and keep captions consistent.

| Figure | Source File | Purpose | Status |
|---|---|---|---|
| System architecture | `docs/diagrams/architecture.md` | Shows Open WebUI, RAG API, retrieval, sync, and observability boundaries | Draft |
| Local deployment | `docs/diagrams/deployment.md` | Shows Docker Compose and Microsoft cloud dependencies | Draft |
| Ingestion sequence | `docs/diagrams/ingestion-sequence.md` | Explains normalization, hashing, chunking, checkpointing, indexing | Draft |
| Query sequence | `docs/diagrams/query-sequence.md` | Explains ACL-aware retrieval and cited answer construction | Draft |
| Operations freshness sequence | `docs/diagrams/operations-sequence.md` | Explains webhook acceptance, durable queue, delta catch-up | Draft |
| Benchmark workflow | `docs/experiments/phase7-benchmark-workflow.md` | Explains experiment procedure and acceptance gates | Draft |
| Latency result table | `docs/experiments/result-table-templates.md` | Provides thesis table format for p50/p95/p99 | Draft |
| Citation/freshness result table | `docs/experiments/result-table-templates.md` | Provides thesis table format for RAG-specific metrics | Draft |

Before final submission:

- Export Mermaid diagrams to PNG or SVG.
- Include raw benchmark command lines in appendix.
- Include hardware and Docker resource limits.
- State whether retrieval provider was `mock` or `qdrant`.
- State whether OpenTelemetry export was enabled.
- Attach the exact dataset version.
- Include limitations for real Microsoft 365 tenant testing.
