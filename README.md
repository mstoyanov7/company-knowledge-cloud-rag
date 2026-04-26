# AI Cloud-RAG Onboarding Chatbot Starter Pack

This repository now contains a runnable Phase 7 proof of concept for an enterprise onboarding RAG backend.

Open WebUI remains the frontend. The repository provides:

- a FastAPI `rag-api` service
- a `sync-worker` skeleton with typed job planning
- shared Pydantic schemas and environment-driven settings
- PostgreSQL, Redis, Qdrant, and Open WebUI via Docker Compose
- ACL-aware retrieval and answer assembly that returns citations and retrieval metadata
- an OpenAI-compatible `/v1` surface so Open WebUI can call the backend locally
- a SharePoint ingestion pipeline with bootstrap and incremental jobs
- a Graph client boundary isolated from extraction, normalization, and indexing
- a OneNote ingestion pipeline with delegated-auth support for site-hosted notebooks
- an Open WebUI Pipe that calls the secured RAG backend while keeping Open WebUI frontend-only
- Microsoft Graph webhook endpoints for SharePoint freshness
- PostgreSQL-backed operations queue, subscription registry, retries, and dead letters
- OpenTelemetry hooks for API, retrieval, and sync job latency/metrics
- Microsoft Entra ID / OIDC configuration for Open WebUI SSO
- backend JWT validation, group/role-to-ACL mapping, and secure audit logging
- a fixed onboarding RAG evaluation dataset and CLI harness
- k6 and Locust benchmark suites for chat API and retrieval-pipeline performance
- benchmark result templates, experiment docs, Mermaid diagrams, and demo packaging notes

## Quick Start

1. Create a virtual environment and install the repo:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

2. Review or copy the root environment file:

```bash
copy .env.example .env
```

3. Start the full local stack from the repository root:

```bash
docker compose up --build
```

4. Open the local apps:

- Open WebUI: `http://localhost:3000`
- RAG API docs: `http://localhost:8080/docs`
- Qdrant: `http://localhost:6333/dashboard`

## Local Commands

Run the API without Docker:

```bash
rag-api
```

Run the sync worker once:

```bash
sync-worker --run-once
```

Run the SharePoint jobs directly:

```bash
sharepoint_bootstrap
sharepoint_incremental
```

Run the OneNote jobs directly:

```bash
onenote_bootstrap
onenote_incremental
```

Run Phase 5 operations jobs directly:

```bash
ops_worker --run-once
subscription_renewal --ensure-sharepoint
sharepoint_delta_catchup
sharepoint_reconciliation
onenote_reconciliation
```

Run the fixed evaluation dataset:

```bash
rag_evaluate --dataset eval/datasets/onboarding_eval.json --output eval/results/latest.json
```

Run a k6 smoke benchmark:

```bash
k6 run benchmarks/k6/smoke.js
```

Run a Locust concurrent-user benchmark:

```bash
locust -f benchmarks/locust/locustfile.py --host http://localhost:8080
```

Call the structured answer endpoint directly:

```bash
curl -X POST http://localhost:8080/api/v1/answer ^
  -H "Authorization: Bearer cloudrag-rag-key" ^
  -H "Content-Type: application/json" ^
  -d "{\"question\":\"What should I do on day one?\",\"user_context\":{\"acl_tags\":[\"public\",\"employees\"]}}"
```

Call the OpenAI-compatible endpoint:

```bash
curl -X POST http://localhost:8080/v1/chat/completions ^
  -H "Authorization: Bearer cloudrag-local-key" ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"mock-onboarding-assistant\",\"messages\":[{\"role\":\"user\",\"content\":\"What benefits should I set up during onboarding?\"}]}"
```

## Repository Shape

- `apps/openwebui`: frontend-only notes and local wiring
- `services/rag-api`: FastAPI API and OpenAI-compatible shim
- `services/sync-worker`: background worker skeleton
- `services/graph-connectors`: SharePoint and OneNote connector boundaries
- `libs/shared-schemas`: shared settings and response models
- `infra`: compose files and infra notes
- `tests`: root smoke and unit tests

## SharePoint Phase

Phase 2 adds a restricted SharePoint scope:

- one configured SharePoint site
- one configured document library
- bootstrap crawl via Microsoft Graph drive delta
- persisted cursor and delta checkpoints
- incremental sync that handles created, updated, and deleted items
- extraction for `txt`, `pdf`, `docx`, and `pptx`
- normalization, hashing, chunking, PostgreSQL metadata writes, and Qdrant vector writes

By default, local development still uses `SHAREPOINT_GRAPH_MODE=mock` so the pipeline is runnable without Microsoft credentials. Switching to `live` uses the real Graph client and the configured site and library scope.

## OneNote Phase

Phase 3 adds a separate OneNote connector and sync pipeline:

- delegated-auth-based Microsoft Graph access
- personal notebook traversal via `/me/onenote/...`
- site-hosted notebook traversal via `/sites/{site-id}/onenote/...`
- notebook, section, and page discovery
- page HTML fetch plus markdown-like normalization
- embedded resource detection hooks for images and attachments
- incremental polling ordered by `lastModifiedDateTime`
- reconciliation for moved or removed pages
- PostgreSQL metadata writes and Qdrant vector writes for changed page content

Important:

- OneNote does not run on app-only auth in this repo
- live OneNote runs are intended from an interactive local shell because device-code auth requires a signed-in user
- the default `.env` keeps `ONENOTE_GRAPH_MODE=mock` so the repo stays runnable without Microsoft credentials
- set `GRAPH_ONENOTE_SCOPE_MODE=me` to index personal notebooks without a SharePoint hostname
- leaving `GRAPH_ONENOTE_NOTEBOOK_SCOPE` empty targets all notebooks in the configured OneNote scope

## Answer Engine Phase

Phase 4 replaces the purely mock answer path with an ACL-aware retrieval layer:

- indexed chunk payloads include tenant, source, ACL tag, and source trace metadata
- Qdrant collections get payload indexes for ACL filter fields
- `/api/v1/answer` resolves the caller's access scope before retrieval
- vector search receives tenant, ACL tag, and source filters before candidate chunks are returned
- optional keyword reranking runs only on authorized chunks
- responses include `answer`, `citations`, `retrieval_meta`, and generation `metadata`
- `apps/openwebui/cloud_rag_pipe.py` can be imported into Open WebUI as a Pipe Function

For direct local calls, include `Authorization: Bearer ${RAG_API_KEY}` when `RAG_API_KEY` is configured.

## Operations Phase

Phase 5 adds freshness and resilience around the existing ingestion pipelines:

- `POST /api/v1/graph/notifications` validates Microsoft Graph webhook URLs and accepts SharePoint change notifications
- `POST /api/v1/graph/lifecycle` handles lifecycle events such as `reauthorizationRequired`
- normal notifications validate `clientState`, persist an idempotency record, enqueue `sharepoint_delta_catchup`, and return `202 Accepted`
- `graph_subscriptions`, `ops_jobs`, `graph_webhook_events`, `dead_letters`, and `ops_metrics` are created in PostgreSQL on demand
- the default Docker `sync-worker` command now runs `ops_worker`, which drains the durable queue and schedules periodic renewal/reconciliation jobs
- SharePoint freshness uses stored delta links after accepted webhooks; OneNote remains scheduled polling/reconciliation only
- failed ops jobs retry with exponential backoff and move to `dead_letters` after `OPS_JOB_MAX_ATTEMPTS`

For real Graph webhooks, expose `rag-api` through a public HTTPS URL and set `GRAPH_NOTIFICATION_BASE_URL`, for example `https://your-domain.example`. Then run:

```bash
subscription_renewal --ensure-sharepoint
ops_worker
```

Local validation test:

```bash
curl -X POST "http://localhost:8080/api/v1/graph/notifications?validationToken=opaque%3Aabc%2B123"
```

The response body should be `opaque:abc+123` with `Content-Type: text/plain`.

## Security and Evaluation Phase

Phase 6 adds SSO/security and reproducible evaluation:

- Open WebUI can be configured for Microsoft Entra ID sign-in with `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_CLIENT_TENANT_ID`, `MICROSOFT_REDIRECT_URI`, and `OPENID_PROVIDER_URL`
- backend auth validates Microsoft identity platform JWTs when `AUTH_ENABLED=true`
- `groups` and `roles` claims map to backend ACL tags through `AUTH_GROUP_SCOPE_MAP_JSON` and `AUTH_ROLE_SCOPE_MAP_JSON`
- when a valid user token is present, `/api/v1/answer` ignores caller-supplied body ACLs and derives retrieval scope from token claims
- security audit events cover authentication success/failure, authorization failure, filtered retrieval denials, and cited-source access
- `eval/datasets/onboarding_eval.json` provides a deterministic onboarding benchmark for retrieval hit rate, document recall, citation correctness, groundedness, and latency

Example local auth mapping:

```env
AUTH_ENABLED=true
AUTH_REQUIRED=true
AUTH_TENANT_ID=<tenant-guid>
AUTH_CLIENT_ID=<backend-api-app-client-id>
AUTH_GROUP_SCOPE_MAP_JSON={"<employees-group-object-id>":["employees"],"<engineering-group-object-id>":["engineering"]}
AUTH_ROLE_SCOPE_MAP_JSON={"RAG.Engineering":["engineering"]}
AUTH_DEFAULT_ACL_TAGS=public
```

For production, do not store `MICROSOFT_CLIENT_SECRET`, `GRAPH_CLIENT_SECRET`, or `WEBUI_SECRET_KEY` in a committed file. Use a secret manager, platform secret injection, or Docker/Kubernetes secrets.

## Performance and Diploma Packaging

Phase 7 adds benchmark and thesis-packaging assets:

- `benchmarks/k6`: smoke, stress, spike, and soak API tests
- `benchmarks/locust`: distributed concurrent chat-user scenario
- `benchmarks/datasets/onboarding_questions.json`: fixed performance dataset
- `benchmarks/results/templates`: CSV and Markdown result table templates
- `benchmarks/scripts/k6_summary_to_csv.py`: k6 summary conversion helper
- `docs/experiments`: benchmark workflow and result table templates
- `docs/diagrams`: Mermaid architecture, deployment, ingestion, query, and operations diagrams
- `docs/demo`: live demo script and thesis figure checklist

The benchmark scripts collect p50/p95/p99 latency, throughput, failure rate, retrieval latency, completion latency, freshness delay, and citation count. Enable OpenTelemetry before benchmark runs to correlate client-side results with backend traces and metrics.
