# AI Cloud-RAG Onboarding Chatbot Starter Pack

This repository now contains a runnable Phase 3 proof of concept for an enterprise onboarding RAG backend.

Open WebUI remains the frontend. The repository provides:

- a FastAPI `rag-api` service
- a `sync-worker` skeleton with typed job planning
- shared Pydantic schemas and environment-driven settings
- PostgreSQL, Redis, Qdrant, and Open WebUI via Docker Compose
- a mock retrieval and answer pipeline that returns citations
- an OpenAI-compatible `/v1` surface so Open WebUI can call the backend locally
- a SharePoint ingestion pipeline with bootstrap and incremental jobs
- a Graph client boundary isolated from extraction, normalization, and indexing
- a OneNote ingestion pipeline with delegated-auth support for site-hosted notebooks

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

Call the structured answer endpoint directly:

```bash
curl -X POST http://localhost:8080/api/v1/answer ^
  -H "Content-Type: application/json" ^
  -d "{\"question\":\"What should I do on day one?\"}"
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
- leaving `GRAPH_ONENOTE_NOTEBOOK_SCOPE` empty targets all notebooks in the configured site
