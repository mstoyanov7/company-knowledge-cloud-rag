# Sync Worker Jobs

This directory is reserved for future queue-backed job entrypoints.

Phase 1 keeps execution in-process through `sync_worker.runner.WorkerRunner`
so the repository stays runnable without a queue framework.
