# billing-service README

Quick reference for running billing-service locally.

## Ports

- API: 8020
- Postgres: 5432

## Key commands

- alembic upgrade head
- pytest tests/smoke
- uvicorn billing.main:app --port 8020

## Gotchas

- Stripe webhooks need the CLI: stripe listen --forward-to localhost:8020/webhooks
