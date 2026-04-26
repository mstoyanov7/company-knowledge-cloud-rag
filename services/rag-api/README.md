# RAG API

`rag-api` is the query orchestration service for the local proof of concept.

Implemented surfaces include:

- `/health`, `/ready`, and `/version`
- `/api/v1/answer` for ACL-aware structured answers with citations and retrieval metadata
- `/api/v1/graph/notifications` for Microsoft Graph change notification delivery
- `/api/v1/graph/lifecycle` for Microsoft Graph lifecycle notifications
- `/v1/models` and `/v1/chat/completions` for Open WebUI compatibility
- provider, retrieval, and reranker interfaces
- mock retrieval for tests plus Qdrant vector retrieval with tenant/source/ACL payload filters
- Microsoft Entra ID JWT validation and claim-derived access scope when enabled
- security audit events for authentication, authorization, retrieval filtering, and citation access

Run locally after `pip install -e ".[dev]"`:

```bash
rag-api
```

Important boundary:

- route handlers call services
- services call interfaces
- retrieval and LLM adapters stay replaceable
- unauthorized chunks are filtered before prompt construction

Webhook behavior:

- validation requests return the URL-decoded `validationToken` as `text/plain` with HTTP 200
- normal notifications validate `clientState`, enqueue durable ops jobs, and return HTTP 202
- lifecycle events enqueue reauthorization or catch-up work instead of doing sync inline

Security behavior:

- `AUTH_ENABLED=true` enables Microsoft identity platform JWT validation.
- `AUTH_REQUIRED=true` requires either a valid backend API key or a valid bearer token.
- Group and role claims are mapped to ACL tags before retrieval.
- Valid bearer-token identity takes precedence over user context supplied in the request body.
- Audit logs avoid token and secret values and can also be written to PostgreSQL.
