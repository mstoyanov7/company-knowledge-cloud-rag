# Sync Worker Jobs

This directory contains the runnable OneNote sync and ops job entrypoints:

- `onenote_bootstrap`
- `onenote_incremental`
- `onenote_reconciliation`
- `ops_worker`

The current implementation runs in-process while durable job state lives in
PostgreSQL, so the repository stays runnable without an external queue framework.
