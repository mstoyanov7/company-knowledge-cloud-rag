# AI Cloud-RAG Company Knowledge Assistant

This repository contains a runnable OneNote-only Cloud-RAG system for company
knowledge and onboarding notes: a FastAPI retrieval-augmented answering backend,
a OneNote ingestion pipeline, and a custom React frontend.

The primary user interface is the topic-first frontend under
`apps/company-knowledge-ui`. The backend provides:

- a FastAPI `rag-api` service with health/readiness endpoints
- `/api/v1/topics` for company knowledge areas (built-in and admin-created)
- `/api/v1/answer` for topic-aware, ACL-aware structured answers with citations,
  attachment download links, and tiered confidence (direct, partial, hedged,
  clarification, or an explicit no-information reply)
- `/api/v1/auth/*` local email/password accounts with sessions, registration,
  and an admin approval workflow (plus optional Microsoft Entra ID / OIDC
  token validation)
- `/api/v1/admin/*` for user management, topic management, system settings,
  and on-demand sync runs
- `/api/v1/documents`, `/api/v1/notebooks`, `/api/v1/trending`, and
  `/api/v1/attachments/{id}/download` for browsing indexed content
- `/api/v1/feedback` for answer feedback capture
- an OpenAI-compatible `/v1` chat-completions API
- an OpenAI-compatible outbound LLM adapter for Ollama-compatible models
- a OneNote ingestion pipeline with delegated Microsoft Graph authentication,
  including readable page attachments indexed as searchable documents
- a once-per-day scheduled OneNote sync, content-hash change detection, and
  reconciliation for moved or deleted pages
- a Redis-backed query-embedding cache (best effort; degrades to a no-op)
- shared Pydantic schemas and environment-driven settings
- PostgreSQL metadata storage, Redis, Qdrant vector storage, and the custom
  frontend via Docker Compose
- ACL-aware retrieval and answer assembly with source citations
- security audit logging, OpenTelemetry hooks, evaluation datasets, and
  performance-test assets

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
the RAG API, background workers, the OneNote poller, and the Company Knowledge UI:

```powershell
.\scripts\start-onenote-stack.ps1 -Build
```

4. Open the local apps:

- Company Knowledge UI: `http://localhost:5173`
- RAG API docs: `http://localhost:8080/docs`
- Qdrant: `http://localhost:6333/dashboard`

5. Sign in. On first run a bootstrap administrator account is created from
`AUTH_BOOTSTRAP_ADMIN_EMAIL` / `AUTH_BOOTSTRAP_ADMIN_PASSWORD`. New users can
register from the login screen and wait for admin approval in the admin panel.

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

Force a sync from the repo root (same operations the admin panel offers):

```powershell
.\scripts\force-sync.ps1              # full bootstrap re-sync (hash-compares every page)
.\scripts\force-incremental-sync.ps1  # changed pages only
```

Run the operations worker:

```bash
ops_worker --run-once
```

Seed the home-screen trending questions with demo data:

```bash
python scripts/seed_trending.py
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
- `services/rag-api`: FastAPI API, answer engine, and OpenAI-compatible shim
- `services/sync-worker`: OneNote sync, daily scheduling, reconciliation, and indexing
- `services/graph-connectors`: OneNote Microsoft Graph connector boundary
- `libs/shared-schemas`: shared settings and response models
- `config`: built-in topic definitions
- `docs`: architecture, data flow, security, and diagram sources
- `eval` / `benchmarks`: evaluation datasets and k6/Locust performance assets
- `infra`: compose files and infra notes
- `scripts`: stack startup, sync, diagnostics, and demo-data helpers
- `tests`: root smoke, unit, and retrieval tests

## OneNote Ingestion

The OneNote pipeline includes:

- delegated-auth Microsoft Graph access
- personal notebook traversal via `/me/onenote/...`
- optional site-hosted notebook traversal via `/sites/{site-id}/onenote/...`
- notebook, section, and page discovery
- page HTML fetch plus markdown-like normalization
- readable attachments (for example `.md`, `.txt`, `.pdf`, `.docx`, `.pptx`)
  extracted and indexed as separate searchable documents that keep their parent
  page title, so questions naming the page or the file both match; originals
  are stored and offered as download links under related answers
- content-shape-aware chunking that keeps procedures (steps, commands, code)
  together so setup answers stay complete
- incremental sync ordered by `lastModifiedDateTime` with content-hash checks
- reconciliation for moved or removed pages
- PostgreSQL metadata writes and Qdrant vector writes for changed content

Important:

- OneNote does not run on app-only auth in this repo.
- Live OneNote runs require a delegated signed-in user.
- Set `GRAPH_ONENOTE_SCOPE_MODE=me` to index personal notebooks.
- Leaving `GRAPH_ONENOTE_NOTEBOOK_SCOPE` empty targets all notebooks in the configured OneNote scope.
- Request pacing and retry settings (`ONENOTE_REQUEST_DELAY_SECONDS`,
  `ONENOTE_RETRY_*`) exist to survive Microsoft Graph 429 throttling.

## Answer Engine

The backend retrieves from the OneNote vector collection and builds grounded answers:

- indexed chunk payloads include tenant, source, ACL tag, and source trace metadata
- Qdrant collections get payload indexes for ACL filter fields
- `/api/v1/answer` resolves the caller's access scope before retrieval
- `topic_id` narrows retrieval by selected knowledge area; when nothing
  confident exists inside the topic, a clearly labeled cross-topic fallback
  searches the rest of the notes before giving up
- topic source filters and ACL tags narrow the caller's access and never broaden it
- hybrid retrieval combines vector similarity with lexical signals
  (`RETRIEVAL_MIN_SEMANTIC_SCORE`, `RETRIEVAL_LEXICAL_WEIGHT`,
  `RETRIEVAL_SEMANTIC_CONFIDENT_SCORE`), with multi-query planning, reranking,
  and LLM-plus-heuristic evidence grading
- query embeddings are cached in Redis (`QUERY_EMBEDDING_CACHE_*`); the cache
  is keyed by question text and model identity only and disables itself on error
- answers are tiered by evidence quality: a confident grounded answer, a
  hedged "related information" answer with an explicit caveat, a quiz-style
  clarification that asks which page the user means (the picked page then
  scopes retrieval via `focus_source_item_ids`), or an explicit
  no-information reply — in that order of preference
- conversational follow-ups are rewritten into standalone questions using the
  session history the frontend sends with each request
- generated answers pass grounding guards (verbatim-critical values must exist
  in the retrieved context) before they are returned; failing answers fall
  back to extractive source text
- responses include `answer`, `citations`, `downloads`, `retrieval_meta`,
  generation `metadata`, and optional `clarification` and suggested questions
- `answer_depth` (`concise` / `normal` / `detailed`) and `answer_style` shape
  the response format and context budget

For direct local calls, include `Authorization: Bearer ${RAG_API_KEY}` when `RAG_API_KEY` is configured.

## Frontend Environment

The custom frontend uses these optional Vite variables:

- `VITE_RAG_API_PROXY_TARGET`: FastAPI target for the local dev proxy, default `http://localhost:8080`
- `VITE_RAG_API_BASE_URL`: absolute backend URL for deployments without the Vite proxy
- `VITE_RAG_API_KEY`: local demo API key sent as `X-RAG-API-Key` when `RAG_API_KEY` is enabled

## Custom Frontend

The Company Knowledge UI keeps the topic-first flow:

1. Sign in (or register and wait for admin approval).
2. Land on the home view: trending questions, recently updated pages, and topics.
3. Work inside a topic-specific assistant workspace.
4. Ask questions with `Enter`; use `Shift+Enter` to add a new line.
5. Review answers as Markdown knowledge cards with citations and download links.

The workspace includes:

- a left rail with per-topic conversation history, pinned chats, search,
  new chat, switching, and deletion
- conversations, pins, and preferences persisted in browser `localStorage`,
  scoped per signed-in user so accounts sharing a browser stay isolated
- a command palette for quick navigation
- clarification prompts rendered as pickable page options
- collapsible source citations and a source detail panel under assistant answers
- attachment download links under answers when the cited pages carry files
- a progressive word-by-word reveal of completed answers
- answer preferences (depth and style) in a preferences panel
- a profile menu and modal for account details
- an admin panel (admin accounts only) for user approval, topic management,
  the daily sync schedule, and a "Run sync now" action
- a light/dark theme toggle stored in browser `localStorage`
- suggested follow-up chips before the first message and after assistant answers

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

Freshness is handled through scheduled sync and reconciliation:

- the automatic OneNote sync runs once per day at `ONENOTE_SYNC_DAILY_TIME`
  (interpreted in `ONENOTE_SYNC_TIMEZONE`), editable in the admin panel
- `ONENOTE_SYNC_INTERVAL_SECONDS` is legacy and no longer drives the poller
- on-demand syncs run from the admin panel ("Run sync now") or the
  `scripts/force-sync.ps1` / `scripts/force-incremental-sync.ps1` helpers
- `ONENOTE_INCREMENTAL_LOOKBACK_SECONDS` controls how far back recent pages are rechecked by hash
- `ops_worker` schedules periodic `onenote_reconciliation`
- failed ops jobs retry with exponential backoff and move to `dead_letters` after `OPS_JOB_MAX_ATTEMPTS`
- `scripts/diagnose-local-stack.ps1` checks the local stack end to end

## Security and Evaluation

- Local accounts use email/password with salted hashing, server-side sessions
  (`AUTH_SESSION_SECRET`, `AUTH_SESSION_TTL_HOURS`), and an admin approval
  workflow (approve / reject / suspend) for new registrations.
- A bootstrap admin is created from `AUTH_BOOTSTRAP_ADMIN_*` settings on first run.
- Backend auth additionally validates Microsoft identity platform JWTs when `AUTH_ENABLED=true`.
- `groups` and `roles` claims map to backend ACL tags through `AUTH_GROUP_SCOPE_MAP_JSON` and `AUTH_ROLE_SCOPE_MAP_JSON`.
- Security audit events cover authentication, authorization, retrieval denials, and cited-source access.
- `eval/datasets/onboarding_eval.json` provides a deterministic onboarding benchmark;
  `eval/live-scenarios.md` documents live demo scenarios.

For production, do not store secrets in a committed file. Use a secret manager,
platform secret injection, Docker secrets, or Kubernetes secrets.

## Ollama LLM and Embeddings

For local real-model answers, run Ollama on the host and set:

```env
DEFAULT_LLM_PROVIDER=ollama
DEFAULT_MODEL_NAME=gpt-oss:120b-cloud
LLM_OPENAI_BASE_URL=http://host.docker.internal:11434/v1
LLM_OPENAI_API_KEY=ollama
```

Semantic retrieval uses real embeddings served by Ollama:

```env
DEFAULT_EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL_NAME=nomic-embed-text
EMBEDDING_VECTOR_SIZE=768
```

Run `ollama pull nomic-embed-text` first. Use `token-hash-v1` as the embedding
provider only for fully offline runs; it is a lexical fallback, not semantic.
`host.docker.internal` lets the Dockerized `rag-api` call Ollama on your PC.
