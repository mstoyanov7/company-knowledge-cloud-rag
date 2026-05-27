# Suggested Monorepo Structure

```text
cloud-rag-diploma/
|-- README.md
|-- .env.example
|-- apps/
|   `-- openwebui/
|-- services/
|   |-- rag-api/
|   |-- sync-worker/
|   `-- graph-connectors/
|       `-- onenote/
|-- libs/
|   `-- shared-schemas/
|-- infra/
|-- docs/
|-- prompts/
`-- tests/
```

## Folder Roles

### `apps/openwebui`

Contains deployment notes, environment variables, and integration code needed for Open WebUI.

### `services/rag-api`

Main query orchestration service.

### `services/sync-worker`

Background jobs for OneNote sync, indexing, retries, and maintenance.

### `services/graph-connectors`

Microsoft Graph connector boundary for OneNote.

### `libs/shared-schemas`

Shared models for chunks, sources, jobs, responses, and config.

### `infra`

Local deployment and future cloud deployment manifests.

## Recommended Service Boundaries

Keep the retrieval API and sync worker separate even if they are deployed together at first.
