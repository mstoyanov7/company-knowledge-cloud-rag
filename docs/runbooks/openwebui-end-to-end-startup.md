# Open WebUI End-to-End Startup Runbook

This runbook starts the system in the correct order so a user can open Open WebUI and ask questions against indexed OneNote content.

Current behavior:

- Open WebUI is the frontend.
- `rag-api` owns retrieval, ACL filtering, prompt construction, and citations.
- OneNote indexing writes chunks to PostgreSQL and Qdrant.
- The backend currently uses the mock LLM adapter unless an Ollama adapter is added.

## 1. Prerequisites

Start Docker Desktop first.

Install Python dependencies once:

```powershell
pip install -e ".[dev]"
```

Make sure `.env` exists:

```powershell
copy .env.example .env
```

## 2. Fast Startup Script

For the first real OneNote import, run:

```powershell
.\scripts\start-onenote-stack.ps1 -Build -Bootstrap
```

For normal later startups, run:

```powershell
.\scripts\start-onenote-stack.ps1
```

The script:

- applies safe OneNote-only local defaults in `.env`
- starts PostgreSQL, Redis, and Qdrant
- runs OneNote bootstrap or incremental sync
- starts the background `sync-worker` service
- starts `rag-api`
- starts Open WebUI
- force-recreates app containers so changed `.env` values are applied
- waits until Open WebUI answers on `http://localhost:3000`
- opens `http://localhost:3000`

Use `-NoEnvUpdate` if you do not want the script to update non-secret OneNote-only `.env` defaults.
Use `-SkipOpsWorker` if you only want the one-off OneNote sync and do not want the background worker container.

If PowerShell blocks script execution, run it through bypass mode for this command only:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-onenote-stack.ps1 -Build -Bootstrap
```

## 3. Required `.env` Values

For OneNote-only testing, keep SharePoint mocked:

```env
SHAREPOINT_GRAPH_MODE=mock
ONENOTE_GRAPH_MODE=live
ONENOTE_AUTH_MODE=device_code
```

Set your OneNote delegated auth values:

```env
GRAPH_ONENOTE_TENANT_ID=<your-tenant-id>
GRAPH_ONENOTE_CLIENT_ID=<your-public-client-app-id>
GRAPH_ONENOTE_SCOPES=Notes.Read
```

Do not include `openid`, `offline_access`, or `profile` in `GRAPH_ONENOTE_SCOPES`.
MSAL reserves those values and will add OIDC scopes itself for device-code auth.

For personal OneNote notebooks, use `/me/onenote` mode and leave the SharePoint site fields empty:

```env
GRAPH_ONENOTE_SCOPE_MODE=me
GRAPH_ONENOTE_SITE_HOSTNAME=
GRAPH_ONENOTE_SITE_SCOPE=
GRAPH_ONENOTE_NOTEBOOK_SCOPE=
```

Leave `GRAPH_ONENOTE_NOTEBOOK_SCOPE` empty to index all notebooks available to your signed-in user.

Only use site mode if your notebooks are hosted in a SharePoint team site:

```env
GRAPH_ONENOTE_SCOPE_MODE=site
GRAPH_ONENOTE_SCOPES=Notes.Read.All Sites.Read.All
GRAPH_ONENOTE_SITE_HOSTNAME=<yourtenant>.sharepoint.com
GRAPH_ONENOTE_SITE_SCOPE=sites/<your-site-name>
GRAPH_ONENOTE_NOTEBOOK_SCOPE=
```

Keep retrieval on Qdrant:

```env
RETRIEVAL_PROVIDER=qdrant
RETRIEVAL_VECTOR_COLLECTIONS=onenote_chunks
AUTH_DEFAULT_ACL_TAGS=public,employees
RAG_API_KEY=cloudrag-rag-key
MOCK_API_KEY=cloudrag-local-key
```

If `RAG_API_PORT=8081`, use port `8081` in all browser and API commands.

If `POSTGRES_PORT=5433` is used to avoid a Windows host port conflict, keep it.
Docker Compose now overrides internal container traffic back to `POSTGRES_PORT=5432`
for `rag-api` and `sync-worker`.

## 4. Start Infrastructure First

Start only databases and vector store:

```powershell
docker compose up -d postgres redis qdrant
```

Verify PostgreSQL:

```powershell
docker compose exec postgres psql -U cloudrag -d cloudrag -c "select current_user, current_database();"
```

Expected:

```text
cloudrag | cloudrag
```

## 5. Index OneNote

Recommended: run the OneNote job inside Docker so it uses the Compose network and connects to `postgres`, not your Windows `localhost`.

```powershell
docker compose run --rm sync-worker python -m sync_worker.jobs.onenote_bootstrap
```

You should see a Microsoft device-code login message. Open the shown URL, enter the code, and sign in.

After the job finishes, verify OneNote documents:

```powershell
docker compose exec postgres psql -U cloudrag -d cloudrag -c "select source_item_id, title, section_path, is_deleted from source_documents where source_system='onenote';"
```

Verify chunks:

```powershell
docker compose exec postgres psql -U cloudrag -d cloudrag -c "select count(*) from chunk_documents where source_system='onenote';"
```

Verify Qdrant collection:

```powershell
Invoke-RestMethod http://localhost:6333/collections/onenote_chunks
```

## 6. Start the RAG API

```powershell
docker compose up -d rag-api
```

Check health:

```powershell
Invoke-RestMethod http://localhost:8081/health
Invoke-RestMethod http://localhost:8081/ready
```

Open API docs:

```text
http://localhost:8081/docs
```

Direct OneNote-only test:

```powershell
Invoke-RestMethod -Method Post http://localhost:8081/api/v1/answer `
  -Headers @{ Authorization = 'Bearer cloudrag-rag-key' } `
  -ContentType "application/json" `
  -Body '{
    "question": "Summarize my OneNote notes",
    "user_context": {
      "tenant_id": "local-tenant",
      "acl_tags": ["public","employees"]
    },
    "source_filters": ["onenote"],
    "top_k": 5
  }'
```

If citations with `source_system = onenote` appear, retrieval is working.

## 7. Start Open WebUI

```powershell
docker compose up -d openwebui
```

Open:

```text
http://localhost:3000
```

Create the first local admin account if Open WebUI asks for one.

## 8. Option A: Use Built-In OpenAI-Compatible Connection

Docker Compose wires Open WebUI to:

```env
OPENAI_API_BASE_URL=http://rag-api:8080/v1
OPENAI_API_KEY=${MOCK_API_KEY}
```

In Open WebUI, select the backend model:

```text
mock-onboarding-assistant
```

Ask:

```text
Summarize my OneNote onboarding notes.
```

This path is easiest, but it has limitations:

- Open WebUI may not display the structured citation objects.
- The OpenAI-compatible endpoint uses default user context.
- For explicit ACL tags and citation display, use the Pipe option below.

## 9. Option B: Recommended Pipe Setup

Use `apps/openwebui/cloud_rag_pipe.py` as an Open WebUI Pipe Function.

In Open WebUI:

1. Go to Admin Panel.
2. Open Functions.
3. Create/import a new Pipe Function.
4. Paste the content of `apps/openwebui/cloud_rag_pipe.py`.
5. Configure valves:

```text
RAG_API_BASE_URL=http://rag-api:8080
RAG_API_KEY=cloudrag-rag-key
DEFAULT_TENANT_ID=local-tenant
DEFAULT_ACL_TAGS=public,employees
TOP_K=5
```

Then select:

```text
Cloud RAG Secure
```

Ask:

```text
What do my OneNote notes say about onboarding?
```

The Pipe calls:

```text
POST /api/v1/answer
```

and appends source citations to the displayed answer.

## 10. Updating OneNote Content

After editing a OneNote page, run incremental sync:

```powershell
docker compose run --rm sync-worker python -m sync_worker.jobs.onenote_incremental
```

Then ask again in Open WebUI.

## 11. Normal Startup Order After Initial Setup

Use this order after OneNote auth and indexing are already working:

```powershell
docker compose up -d postgres redis qdrant
docker compose run --rm sync-worker python -m sync_worker.jobs.onenote_incremental
docker compose up -d rag-api
docker compose up -d openwebui
```

Then open:

```text
http://localhost:3000
```

## 12. Troubleshooting

If the OneNote job says `role "cloudrag" does not exist`, do not run it from Windows host Python. Run it inside Docker:

```powershell
docker compose run --rm sync-worker python -m sync_worker.jobs.onenote_bootstrap
```

If the OneNote job says `connection refused` on `postgres:5433`, rebuild/recreate
the worker with the updated Compose environment overrides:

```powershell
docker compose up -d --build rag-api
docker compose run --rm --build sync-worker python -m sync_worker.jobs.onenote_bootstrap
```

If the OneNote job says `You cannot use any scope value that is reserved`, remove
OIDC scopes from `GRAPH_ONENOTE_SCOPES`:

```env
GRAPH_ONENOTE_SCOPES=Notes.Read
```

If the OneNote job calls `contoso.sharepoint.com`, you are still in site mode or still have placeholder site values. For personal notebooks, set:

```env
GRAPH_ONENOTE_SCOPE_MODE=me
GRAPH_ONENOTE_SITE_HOSTNAME=
GRAPH_ONENOTE_SITE_SCOPE=
```

If Open WebUI cannot reach the backend, remember:

- From your browser: use `http://localhost:8081`.
- From Open WebUI container to rag-api container: use `http://rag-api:8080`.

If answers are generic or mock-like, that is expected until an Ollama/OpenAI-compatible LLM adapter is added to `rag-api`.
