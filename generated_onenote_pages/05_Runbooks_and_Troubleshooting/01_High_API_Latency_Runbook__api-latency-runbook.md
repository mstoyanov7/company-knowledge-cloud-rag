# API Latency Runbook

_Attached to the "High API Latency Runbook" runbook in the Runbooks and Troubleshooting section, owned by Platform Team._

Condensed steps for paging engineers at 3am.

## Alert

- p95 > 800ms for 5 min

## First checks

- API Overview dashboard
- DB pool saturation
- Recent deploy in #releases

## Mitigations

- Scale api-gateway to 6 replicas
- Roll back last deploy if it correlates
