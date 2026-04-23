# Sync Worker

`sync-worker` is the ingestion and indexing service.

Current behavior:

- runs `sharepoint_bootstrap` for the initial crawl
- runs `sharepoint_incremental` for delta-based refreshes
- runs `onenote_bootstrap` for a OneNote site notebook bootstrap
- runs `onenote_incremental` for last-modified polling and reconciliation
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
```

Run incremental sync continuously:

```bash
sharepoint_incremental --run-loop
onenote_incremental --run-loop
```

OneNote live runs require delegated auth, so they are intended from a local shell
rather than as the default Docker background process.
