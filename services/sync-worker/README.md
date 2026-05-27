# Sync Worker

`sync-worker` is the OneNote ingestion and indexing service.

Current behavior:

- runs `onenote_bootstrap` for the initial OneNote crawl
- runs `onenote_incremental` for last-modified polling plus lookback hash checks
- runs `onenote_reconciliation` for deleted or moved page cleanup
- runs `ops_worker` for scheduled reconciliation, retries, and dead letters
- parses OneNote page HTML into markdown-like text
- normalizes OneNote pages into the shared document schema
- writes document metadata into PostgreSQL
- writes chunk vectors into Qdrant with deterministic embeddings

Run once locally:

```bash
onenote_bootstrap
onenote_incremental
onenote_reconciliation
ops_worker --run-once
```

Run sync continuously:

```bash
onenote_incremental --run-loop
ops_worker
```

OneNote live runs require delegated auth, so device-code sign-in must be completed
for the configured Microsoft account. The Docker Compose `sync-worker` service
runs `ops_worker` by default, while `onenote-poller` runs the 60-second polling
loop when enabled in Compose.
