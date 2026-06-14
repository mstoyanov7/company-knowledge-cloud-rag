# billing-service README

_Attached to the "Billing Service Setup" project setup record in the Project Setups section, owned by Payments Team._

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
