# AI Cloud-RAG OneNote Assistant

This repository contains a runnable OneNote-only Cloud-RAG proof of concept for
company knowledge and onboarding notes.

Open WebUI remains the frontend. The backend provides:

- a FastAPI `rag-api` service
- an OpenAI-compatible `/v1` API so Open WebUI can call the backend locally
- an OpenAI-compatible outbound LLM adapter for Ollama-compatible models
- a OneNote ingestion pipeline with delegated Microsoft Graph authentication
- scheduled OneNote polling, lookback-based content hash checks, and reconciliation
- shared Pydantic schemas and environment-driven settings
- PostgreSQL metadata storage, Redis, Qdrant vector storage, and Open WebUI via Docker Compose
- ACL-aware retrieval and answer assembly with source-title citations
- Microsoft Entra ID / OIDC configuration for Open WebUI SSO and backend token validation
- secure audit logging, OpenTelemetry hooks, evaluation datasets, and performance-test assets

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

3. Start the local stack from the repository root:

```bash
docker compose up --build
```

4. Open the local apps:

- Open WebUI: `http://localhost:3000`
- RAG API docs: `http://localhost:8081/docs`
- Qdrant: `http://localhost:6333/dashboard`

## Local Commands

Run the API without Docker:

```bash
rag-api
```

Run the sync worker planner once:

```bash
sync-worker --run-once
```

Run OneNote jobs directly:

```bash
onenote_bootstrap
onenote_incremental
onenote_reconciliation
```

Run the operations worker:

```bash
ops_worker --run-once
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
locust -f benchmarks/locust/locustfile.py --host http://localhost:8081
```

Call the structured answer endpoint directly:

```bash
curl -X POST http://localhost:8081/api/v1/answer ^
  -H "Authorization: Bearer cloudrag-rag-key" ^
  -H "Content-Type: application/json" ^
  -d "{\"question\":\"What do my OneNote notes say about onboarding?\",\"user_context\":{\"acl_tags\":[\"public\",\"employees\"]}}"
```

Call the OpenAI-compatible endpoint:

```bash
curl -X POST http://localhost:8081/v1/chat/completions ^
  -H "Authorization: Bearer cloudrag-local-key" ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"mock-onboarding-assistant\",\"messages\":[{\"role\":\"user\",\"content\":\"Summarize my OneNote onboarding notes.\"}]}"
```

## Repository Shape

- `apps/openwebui`: frontend-only notes and local wiring
- `services/rag-api`: FastAPI API and OpenAI-compatible shim
- `services/sync-worker`: OneNote sync, polling, reconciliation, and indexing
- `services/graph-connectors`: OneNote Microsoft Graph connector boundary
- `libs/shared-schemas`: shared settings and response models
- `infra`: compose files and infra notes
- `tests`: root smoke, unit, and retrieval tests

## OneNote Ingestion

The OneNote pipeline includes:

- delegated-auth Microsoft Graph access
- personal notebook traversal via `/me/onenote/...`
- optional site-hosted notebook traversal via `/sites/{site-id}/onenote/...`
- notebook, section, and page discovery
- page HTML fetch plus markdown-like normalization
- embedded resource detection hooks for images and attachments
- incremental polling ordered by `lastModifiedDateTime`
- configurable lookback rechecks using content hashes for freshness
- reconciliation for moved or removed pages
- PostgreSQL metadata writes and Qdrant vector writes for changed page content

Important:

- OneNote does not run on app-only auth in this repo.
- Live OneNote runs require a delegated signed-in user.
- Set `GRAPH_ONENOTE_SCOPE_MODE=me` to index personal notebooks.
- Leaving `GRAPH_ONENOTE_NOTEBOOK_SCOPE` empty targets all notebooks in the configured OneNote scope.

## Answer Engine

The backend retrieves from the OneNote vector collection and builds grounded answers:

- indexed chunk payloads include tenant, source, ACL tag, and source trace metadata
- Qdrant collections get payload indexes for ACL filter fields
- `/api/v1/answer` resolves the caller's access scope before retrieval
- vector search receives tenant, ACL tag, and source filters before candidate chunks are returned
- query planning, hybrid retrieval, reranking, evidence grading, and sufficiency checks reduce wrong-topic answers
- responses include `answer`, `citations`, `retrieval_meta`, and generation `metadata`
- Open WebUI calls the backend through the OpenAI-compatible `/v1` API or the optional Pipe Function

For direct local calls, include `Authorization: Bearer ${RAG_API_KEY}` when `RAG_API_KEY` is configured.

## Operations

Freshness is handled through OneNote polling and reconciliation:

- `onenote-poller` runs `onenote_incremental --run-loop`
- `ONENOTE_SYNC_INTERVAL_SECONDS` controls polling frequency
- `ONENOTE_INCREMENTAL_LOOKBACK_SECONDS` controls how far back recent pages are rechecked by hash
- `ops_worker` schedules periodic `onenote_reconciliation`
- failed ops jobs retry with exponential backoff and move to `dead_letters` after `OPS_JOB_MAX_ATTEMPTS`

## Security and Evaluation

- Open WebUI can be configured for Microsoft Entra ID sign-in.
- Backend auth validates Microsoft identity platform JWTs when `AUTH_ENABLED=true`.
- `groups` and `roles` claims map to backend ACL tags through `AUTH_GROUP_SCOPE_MAP_JSON` and `AUTH_ROLE_SCOPE_MAP_JSON`.
- Security audit events cover authentication, authorization, retrieval denials, and cited-source access.
- `eval/datasets/onboarding_eval.json` provides a deterministic onboarding benchmark.

For production, do not store secrets in a committed file. Use a secret manager,
platform secret injection, Docker secrets, or Kubernetes secrets.

## Ollama LLM

For local real-model answers, run Ollama on the host and set:

```env
DEFAULT_LLM_PROVIDER=ollama
DEFAULT_MODEL_NAME=qwen3.5:cloud
LLM_OPENAI_BASE_URL=http://host.docker.internal:11434/v1
LLM_OPENAI_API_KEY=ollama
```

`host.docker.internal` lets the Dockerized `rag-api` call Ollama on your PC.
