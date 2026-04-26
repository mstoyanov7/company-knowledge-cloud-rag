# Environment Files

Use the repository root `.env` file for local development.

The compose file under `infra/` references `../.env` so both:

- `docker compose up --build`
- `docker compose -f infra/docker-compose.yml up --build`

use the same settings source.

## Secrets Guidance

The root `.env` file is for local development only and is ignored by Git.

For shared, staging, or production environments:

- store `GRAPH_CLIENT_SECRET`, `MICROSOFT_CLIENT_SECRET`, `WEBUI_SECRET_KEY`, and any provider API keys in a managed secret store
- inject secrets through the platform, for example Docker secrets, Kubernetes secrets, GitHub Actions secrets, Azure Key Vault, or equivalent
- keep `.env.example` limited to placeholder values and non-secret defaults
- rotate secrets after demos, accidental exposure, or membership changes
- do not paste bearer tokens, client secrets, or private keys into audit logs, tickets, or committed docs

Recommended split:

- `.env.example`: documented non-secret defaults
- local `.env`: developer-only throwaway values
- production: platform-managed secret injection plus non-secret config in deployment manifests
