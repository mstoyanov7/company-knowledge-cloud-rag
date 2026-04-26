# Live Demo Script

## Setup Before Recording

1. Start Docker Desktop.
2. Ensure `.env` uses a known port, for example `RAG_API_PORT=8080`.
3. Start the stack:

```powershell
docker compose up --build
```

4. Confirm health:

```powershell
Invoke-RestMethod http://localhost:8080/health
Invoke-RestMethod http://localhost:8080/ready
```

5. Run the deterministic evaluation once:

```powershell
$env:RETRIEVAL_PROVIDER='mock'
$env:SECURITY_AUDIT_ENABLED='false'
rag_evaluate --dataset eval/datasets/onboarding_eval.json --output eval/results/latest.json
```

## Demo Flow

1. Show architecture diagram: `docs/diagrams/architecture.md`.
2. Open RAG API docs: `http://localhost:8080/docs`.
3. Ask a public onboarding question:

```powershell
Invoke-RestMethod -Method Post http://localhost:8080/api/v1/answer `
  -Headers @{ Authorization = 'Bearer cloudrag-rag-key' } `
  -ContentType 'application/json' `
  -Body '{"question":"What should I do on day one?","user_context":{"acl_tags":["public","employees"]}}'
```

4. Ask an engineering-only question as an employee and show zero citations.
5. Ask the same question as engineering and show the citation.
6. Run a webhook validation check:

```powershell
Invoke-WebRequest -Method Post "http://localhost:8080/api/v1/graph/notifications?validationToken=demo%3Atoken"
```

7. Run k6 smoke:

```powershell
$env:BASE_URL='http://localhost:8080'
$env:RAG_API_KEY='cloudrag-rag-key'
$env:BENCHMARK_RUN_ID='demo-smoke'
k6 run benchmarks/k6/smoke.js
```

8. Show result template: `benchmarks/results/templates/benchmark-summary.md`.

## Talking Points

- Open WebUI remains only the frontend.
- Retrieval, ACL filtering, citations, and sync are backend-owned.
- Unauthorized chunks are filtered before prompt construction.
- SharePoint freshness uses Graph notifications plus delta catch-up.
- OneNote uses delegated auth and scheduled reconciliation.
- Benchmarks capture total latency, retrieval latency, completion latency, freshness delay, citations, throughput, and failures.
