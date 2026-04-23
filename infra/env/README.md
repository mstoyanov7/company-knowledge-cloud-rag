# Environment Files

Use the repository root `.env` file for local development.

The compose file under `infra/` references `../.env` so both:

- `docker compose up --build`
- `docker compose -f infra/docker-compose.yml up --build`

use the same settings source.
