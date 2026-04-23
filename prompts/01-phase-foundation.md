# Codex Prompt - Phase 1 Foundation

Goal:
Create the initial monorepo scaffold and make the project runnable locally.

Tasks:
- create Python project structure for `services/rag-api`, `services/sync-worker`, and `services/graph-connectors`
- create `libs/shared-schemas` for common Pydantic models
- create `.env.example`
- create `infra/docker-compose.yml` with PostgreSQL, Redis, and one vector store
- create a FastAPI app in `services/rag-api`
- add `/health`, `/ready`, and `/version` endpoints
- add a configuration module that loads environment variables into typed settings
- add a provider-agnostic LLM adapter interface with at least one mock implementation
- add a retrieval interface and a mock implementation
- add a standard API response schema for `answer`, `citations`, and `metadata`
- add unit tests for config loading and health endpoints
- add README files for each top-level service

Standards:
- Python 3.12
- Pydantic v2
- typed code
- clear package boundaries
- no business logic in route handlers
- route handlers call services
- services call interfaces

Definition of done:
- `docker compose up` starts core infra
- FastAPI runs locally
- health endpoints pass
- project structure is clean and documented
