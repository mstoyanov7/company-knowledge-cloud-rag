# Sync Worker

`sync-worker` is the Phase 1 skeleton for the ingestion and indexing path.

Current behavior:

- loads typed settings from the shared config module
- instantiates SharePoint and OneNote connector boundaries
- plans placeholder incremental and reconciliation jobs
- logs the planned work on a fixed interval

Run once locally:

```bash
sync-worker --run-once
```
