# RAG API

`rag-api` is the query orchestration service for the local proof of concept.

Phase 1 includes:

- `/health`, `/ready`, and `/version`
- `/api/v1/answer` for structured answers with citations
- `/v1/models` and `/v1/chat/completions` for Open WebUI compatibility
- provider and retrieval interfaces with mock implementations

Run locally after `pip install -e ".[dev]"`:

```bash
rag-api
```

Important boundary:

- route handlers call services
- services call interfaces
- retrieval and LLM adapters stay replaceable
