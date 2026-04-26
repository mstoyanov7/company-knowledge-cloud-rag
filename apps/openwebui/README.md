# Open WebUI

Open WebUI stays frontend-only in this repository.

The local Docker Compose stack wires Open WebUI to the FastAPI backend through the
OpenAI-compatible endpoints exposed by `rag-api`:

- `OPENAI_API_BASE_URL=http://rag-api:8080/v1`
- `OPENAI_API_KEY=${MOCK_API_KEY}`

That lets Open WebUI talk to the backend without moving retrieval or citation logic
into the frontend.

For ACL-aware retrieval, import `cloud_rag_pipe.py` into Open WebUI as a Pipe
Function. Configure it with:

- `RAG_API_BASE_URL=http://rag-api:8080` inside Docker Compose, or `http://localhost:8081` from the host
- `RAG_API_KEY` matching backend `RAG_API_KEY` when that backend setting is configured
- `DEFAULT_ACL_TAGS` as comma-separated ACL tags for users of the pipe, for example `public,employees`
- `FORWARD_USER_TOKEN=true` to forward an OAuth/OIDC token from Open WebUI user metadata when available

The pipe calls `/api/v1/answer` and displays the backend answer with source citations.

## Microsoft Entra ID SSO

Open WebUI can be configured as the frontend SSO client with Microsoft Entra ID.
Set these environment variables in `.env` for the `openwebui` service:

- `WEBUI_URL=https://your-open-webui-domain`
- `ENABLE_OAUTH_SIGNUP=true`
- `MICROSOFT_CLIENT_ID=<open-webui-app-client-id>`
- `MICROSOFT_CLIENT_SECRET=<secret-from-entra>`
- `MICROSOFT_CLIENT_TENANT_ID=<tenant-guid>`
- `MICROSOFT_REDIRECT_URI=https://your-open-webui-domain/oauth/microsoft/callback`
- `OPENID_PROVIDER_URL=https://login.microsoftonline.com/<tenant-guid>/v2.0/.well-known/openid-configuration`
- `OAUTH_SCOPES=openid email profile`
- `OAUTH_GROUP_CLAIM=groups`
- `ENABLE_OAUTH_GROUP_MANAGEMENT=true`

The RAG backend still owns retrieval authorization. Configure backend `AUTH_*`
settings separately so `/api/v1/answer` validates tokens and derives ACL tags
from Entra `groups` and `roles` claims.

Notes:

- Open WebUI persists configuration in its data volume.
- If you change OpenAI connection settings and need a clean reset, remove the
  `open-webui-data` volume and recreate the stack.
