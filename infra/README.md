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
- Open WebUI

Operational tables are created lazily by the services in PostgreSQL:

- `ops_jobs` for durable webhook, renewal, and reconciliation work
- `graph_subscriptions` for Microsoft Graph subscription state
- `graph_webhook_events` for notification idempotency
- `dead_letters` for exhausted jobs
- `ops_metrics` for lightweight local metric snapshots

Microsoft Graph webhooks require a public HTTPS URL. For local development, use
a tunnel such as ngrok or Cloudflare Tunnel and set `GRAPH_NOTIFICATION_BASE_URL`
to that HTTPS origin.
