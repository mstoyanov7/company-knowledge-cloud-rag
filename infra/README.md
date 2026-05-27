# Infrastructure

The local stack is defined in:

- `docker-compose.yml` at the repository root for the normal `docker compose up` flow
- `infra/docker-compose.yml` as the documented infra location from the starter pack

Services started locally:

- PostgreSQL
- Redis
- Qdrant
- `rag-api`
- `sync-worker`
- `onenote-poller`
- Open WebUI

Operational tables are created lazily by the services in PostgreSQL:

- `ops_jobs` for durable reconciliation and retry work
- `dead_letters` for exhausted jobs
- `ops_metrics` for lightweight local metric snapshots
- `security_audit_events`
- `evaluation_runs`

OneNote freshness is handled by scheduled polling and reconciliation, not by
Microsoft Graph notifications.
