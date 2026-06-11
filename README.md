# AI Cloud-RAG Company Knowledge Assistant

This repository contains a runnable OneNote-only Cloud-RAG proof of concept for
company knowledge and onboarding notes.

The primary user interface is now a custom topic-first frontend under
`apps/company-knowledge-ui`. The backend provides:

- a FastAPI `rag-api` service
- `/api/v1/topics` for company knowledge areas
- `/api/v1/answer` for topic-aware, ACL-aware structured answers
- an OpenAI-compatible `/v1` chat-completions API
- an OpenAI-compatible outbound LLM adapter for Ollama-compatible models
- a OneNote ingestion pipeline with delegated Microsoft Graph authentication
- scheduled OneNote polling, lookback-based content hash checks, and reconciliation
- shared Pydantic schemas and environment-driven settings
- PostgreSQL metadata storage, Redis, Qdrant vector storage, and the custom frontend via Docker Compose
- ACL-aware retrieval and answer assembly with source-title citations
- Microsoft Entra ID / OIDC backend token validation
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

Or use the PowerShell startup script, which starts PostgreSQL, Redis, Qdrant,
the RAG API, background workers, OneNote polling, and the Company Knowledge UI:

```powershell
.\scripts\start-onenote-stack.ps1 -Build
```

4. Open the local apps:

- Company Knowledge UI: `http://localhost:5173`
- RAG API docs: `http://localhost:8080/docs`
- Qdrant: `http://localhost:6333/dashboard`

## Local Commands

Run the API without Docker:

```bash
rag-api
```

Run the custom frontend without Docker:

```bash
cd apps/company-knowledge-ui
npm install
$env:VITE_RAG_API_PROXY_TARGET="http://localhost:8080"
$env:VITE_RAG_API_KEY="cloudrag-rag-key"
npm run dev
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
locust -f benchmarks/locust/locustfile.py --host http://localhost:8080
```

Call the structured answer endpoint directly:

```bash
curl -X POST http://localhost:8080/api/v1/answer ^
  -H "Authorization: Bearer cloudrag-rag-key" ^
  -H "Content-Type: application/json" ^
  -d "{\"topic_id\":\"onboarding\",\"question\":\"What do my OneNote notes say about onboarding?\",\"user_context\":{\"acl_tags\":[\"public\",\"employees\"]}}"
```

List configured topics:

```bash
curl http://localhost:8080/api/v1/topics ^
  -H "Authorization: Bearer cloudrag-rag-key"
```

Call the OpenAI-compatible endpoint:

```bash
curl -X POST http://localhost:8080/v1/chat/completions ^
  -H "Authorization: Bearer cloudrag-local-key" ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"mock-onboarding-assistant\",\"messages\":[{\"role\":\"user\",\"content\":\"Summarize my OneNote onboarding notes.\"}]}"
```

## Repository Shape

- `apps/company-knowledge-ui`: React + TypeScript topic-first frontend
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
- `topic_id` narrows retrieval by selected knowledge area before candidates are returned
- topic source filters are combined with caller source filters without broadening access
- topic ACL tags narrow the caller's allowed ACL tags and never bypass user ACL checks
- vector search receives tenant, ACL tag, and source filters before candidate chunks are returned
- query planning, hybrid retrieval, reranking, evidence grading, and sufficiency checks reduce wrong-topic answers
- responses include `answer`, `citations`, `retrieval_meta`, and generation `metadata`
- the custom frontend renders only the answer, citations, and topic follow-up questions

For direct local calls, include `Authorization: Bearer ${RAG_API_KEY}` when `RAG_API_KEY` is configured.

## Frontend Environment

The custom frontend uses these optional Vite variables:

- `VITE_RAG_API_PROXY_TARGET`: FastAPI target for the local dev proxy, default `http://localhost:8080`
- `VITE_RAG_API_BASE_URL`: absolute backend URL for deployments without the Vite proxy
- `VITE_RAG_API_KEY`: local demo API key sent as `X-RAG-API-Key` when `RAG_API_KEY` is enabled

## Custom Frontend

The Company Knowledge UI keeps the topic-first flow:

1. Choose a knowledge topic.
2. Work inside a topic-specific assistant workspace.
3. Ask questions with `Enter`; use `Shift+Enter` to add a new line.
4. Review answers as Markdown knowledge cards with compact citations.

The chat workspace includes:

- a familiar left conversation sidebar
- per-topic conversation history stored in browser `localStorage`
- new chat, chat switching, chat deletion, and conversation search
- right-aligned user bubbles and left-aligned assistant bubbles
- a bottom composer with multiline input, `Enter` send, and `Shift+Enter` newline
- a light/dark theme toggle stored in browser `localStorage`
- suggested follow-up chips before the first message and after assistant answers
- collapsible source citations under assistant answers
- detailed answer requests sent with `answer_depth: "detailed"`

To verify detailed answer mode, open the browser developer tools Network tab and
inspect `/api/v1/answer`. The JSON request should include:

```json
{
  "topic_id": "onboarding",
  "conversation_id": "conv-...",
  "answer_depth": "detailed",
  "question": "..."
}
```

If answers are still too short, first confirm the retrieved source contains more
than one relevant paragraph and that `LLM_MAX_TOKENS` is set high enough, for
example `1400`.

## Operations

Freshness is handled through OneNote polling and reconciliation:

- `onenote-poller` runs `onenote_incremental --run-loop`
- `ONENOTE_SYNC_INTERVAL_SECONDS` controls polling frequency
- `ONENOTE_INCREMENTAL_LOOKBACK_SECONDS` controls how far back recent pages are rechecked by hash
- `ops_worker` schedules periodic `onenote_reconciliation`
- failed ops jobs retry with exponential backoff and move to `dead_letters` after `OPS_JOB_MAX_ATTEMPTS`

## Security and Evaluation

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
