# RAG API

`rag-api` is the query orchestration service for the local proof of concept.

Implemented surfaces include:

- `/health`, `/ready`, and `/version`
- `/api/v1/topics` for configured company knowledge topics
- `/api/v1/answer` for topic-aware, ACL-aware structured answers with citations and retrieval metadata
- `/api/v1/answer/stream` for SSE answer deltas followed by final citations and metadata
- `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/me`, `/api/v1/auth/logout`, and `PATCH /api/v1/auth/me` for local email/password sessions
- `/api/v1/notebooks` for ACL-filtered Notebook -> Section -> Page hierarchy
- `/api/v1/documents?sort=recently_updated&limit=N` for ACL-filtered recent source pages
- `/api/v1/trending?window=30d&limit=N` for tenant and ACL-scoped popular questions
- `/api/v1/feedback` for answer ratings and gap reports, plus `GET /api/v1/feedback` for the caller's records
- `/api/v1/graph/notifications` for Microsoft Graph change notification delivery
- `/api/v1/graph/lifecycle` for Microsoft Graph lifecycle notifications
- `/v1/models` and `/v1/chat/completions` for Open WebUI compatibility
- provider, retrieval, and reranker interfaces
- mock retrieval for tests plus Qdrant vector retrieval with tenant/source/ACL payload filters
- Microsoft Entra ID JWT validation and claim-derived access scope when enabled
- SQLAlchemy app datastore for local users, sessions, query logs, and feedback
- security audit events for authentication, authorization, retrieval filtering, and citation access

Run locally after `pip install -e ".[dev]"`:

```bash
rag-api
```

Important boundary:

- route handlers call services
- services call interfaces
- retrieval and LLM adapters stay replaceable
- user ACL is resolved before topic scope, retrieval, rerank, and answer construction
- unauthorized chunks are filtered before prompt construction
- `topic_id` narrows source filters, ACL tags, retrieval context, and follow-up questions
- `answer_depth` supports `concise`, `normal`, and `detailed`; the custom frontend sends `detailed`
- detailed answers ask the LLM for a summary, relevant details, steps or bullets when applicable, and sources

Webhook behavior:

- validation requests return the URL-decoded `validationToken` as `text/plain` with HTTP 200
- normal notifications validate `clientState`, enqueue durable ops jobs, and return HTTP 202
- lifecycle events enqueue reauthorization or catch-up work instead of doing sync inline

Security behavior:

- `AUTH_ENABLED=true` enables Microsoft identity platform JWT validation.
- `AUTH_REQUIRED=true` requires either a valid backend API key or a valid bearer token.
- Group and role claims are mapped to ACL tags before retrieval.
- Valid bearer-token identity takes precedence over user context supplied in the request body.
- Local session bearer tokens take precedence over the shared `X-RAG-API-Key`; the API key remains supported for legacy clients.
- Audit logs avoid token and secret values and can also be written to PostgreSQL.

App datastore settings:

- `APP_DATABASE_URL` defaults to `sqlite:///./.cache/rag_api.sqlite3` for local development.
- `AUTH_SESSION_SECRET` signs local session JWTs; set a long random value outside local development.
- `AUTH_SESSION_TTL_HOURS` controls session lifetime.
- `AUTH_REGISTRATION_TENANT_ID` and `AUTH_REGISTRATION_ACL_TAGS` control the default tenant and ACL tags assigned to locally registered users.

Streaming note:

- The current LLM port exposes non-streaming generation. `/api/v1/answer/stream` therefore emits chunked SSE deltas from the completed grounded answer and sends the full `AnswerResponse` in the final event. Provider token streaming can be added behind the LLM adapter without changing the frontend stream contract.
