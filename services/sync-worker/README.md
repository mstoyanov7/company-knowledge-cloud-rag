# Sync Worker

`sync-worker` is the ingestion and indexing service.

Current behavior:

- runs `sharepoint_bootstrap` for the initial crawl
- runs `sharepoint_incremental` for delta-based refreshes
- runs `onenote_bootstrap` for a OneNote site notebook bootstrap
- runs `onenote_incremental` for last-modified polling and reconciliation
- runs `ops_worker` for webhook-triggered catch-up jobs, retries, renewals, and dead letters
- extracts `txt`, `pdf`, `docx`, and `pptx`
- parses OneNote page HTML into markdown-like text
- normalizes files into the shared document schema
- writes document metadata into PostgreSQL
- writes chunk vectors into Qdrant with deterministic embeddings

Run once locally:

```bash
sharepoint_bootstrap
sharepoint_incremental
onenote_bootstrap
onenote_incremental
ops_worker --run-once
subscription_renewal --ensure-sharepoint
sharepoint_delta_catchup
sharepoint_reconciliation
onenote_reconciliation
```

Run incremental sync continuously:

```bash
sharepoint_incremental --run-loop
onenote_incremental --run-loop
ops_worker
```

OneNote live runs require delegated auth, so they are intended from a local shell
rather than as the default Docker background process.

The Docker Compose `sync-worker` service runs `ops_worker` by default. It stores
durable jobs in PostgreSQL, retries transient failures with exponential backoff,
and moves exhausted jobs into `dead_letters`.
