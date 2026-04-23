# Suggested Monorepo Structure

```text
cloud-rag-diploma/
├── README.md
├── .env.example
├── apps/
│   └── openwebui/
│       └── README.md
├── services/
│   ├── rag-api/
│   │   ├── app/
│   │   ├── tests/
│   │   └── README.md
│   ├── sync-worker/
│   │   ├── app/
│   │   ├── jobs/
│   │   └── README.md
│   └── graph-connectors/
│       ├── sharepoint/
│       ├── onenote/
│       └── README.md
├── libs/
│   └── shared-schemas/
│       ├── python/
│       └── README.md
├── infra/
│   ├── docker-compose.yml
│   ├── env/
│   └── README.md
├── docs/
│   ├── 01-solution-overview.md
│   ├── 02-architecture.md
│   ├── 03-data-flow.md
│   ├── 04-sync-strategy.md
│   ├── 05-security-acl.md
│   ├── 06-implementation-phases.md
│   ├── 07-diploma-novelty.md
│   └── 08-repo-structure.md
├── prompts/
│   ├── 00-master-prompt.md
│   ├── 01-phase-foundation.md
│   ├── 02-phase-sharepoint.md
│   ├── 03-phase-onenote.md
│   ├── 04-phase-answer-engine.md
│   ├── 05-phase-ops.md
│   └── 06-reviewer-prompt.md
└── tests/
    └── README.md
```

## Folder roles

### `apps/openwebui`
Contains deployment notes, environment variables, and any custom pipes or integration code needed for Open WebUI.

### `services/rag-api`
Main query orchestration service.

### `services/sync-worker`
Background jobs for sync, indexing, retries, and maintenance.

### `services/graph-connectors`
Source-specific logic for SharePoint and OneNote.

### `libs/shared-schemas`
Shared models for chunks, sources, jobs, responses, and config.

### `infra`
Local deployment and future cloud deployment manifests.

## Recommended service boundaries

Keep the retrieval API and sync worker separate even if they are deployed together at first.
