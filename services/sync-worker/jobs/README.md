# Sync Worker Jobs

This directory contains the runnable sync and ops job entrypoints:

- `sharepoint_bootstrap`
- `sharepoint_incremental`
- `onenote_bootstrap`
- `onenote_incremental`
- `ops_worker`
- `subscription_renewal`
- `sharepoint_delta_catchup`
- `sharepoint_reconciliation`
- `onenote_reconciliation`

The current implementation runs in-process while durable job state lives in
PostgreSQL, so the repository stays runnable without an external queue framework.
