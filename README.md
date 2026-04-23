# AI Cloud-RAG Onboarding Chatbot Starter Pack

This repository now contains a runnable Phase 1 proof of concept for an enterprise onboarding RAG backend.

Open WebUI remains the frontend. The repository provides:

- a FastAPI `rag-api` service
- a `sync-worker` skeleton with typed job planning
- shared Pydantic schemas and environment-driven settings
- PostgreSQL, Redis, Qdrant, and Open WebUI via Docker Compose
- a mock retrieval and answer pipeline that returns citations
- an OpenAI-compatible `/v1` surface so Open WebUI can call the backend locally

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

## Phase 1 Scope

This phase intentionally keeps retrieval and generation mocked so the repository stays runnable while preserving the real service boundaries needed for later SharePoint, OneNote, ACL, and reranking work.
