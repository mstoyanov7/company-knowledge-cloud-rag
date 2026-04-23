# Open WebUI

Open WebUI stays frontend-only in this repository.

The local Docker Compose stack wires Open WebUI to the FastAPI backend through the
OpenAI-compatible endpoints exposed by `rag-api`:

- `OPENAI_API_BASE_URL=http://rag-api:8080/v1`
- `OPENAI_API_KEY=${MOCK_API_KEY}`

That lets Open WebUI talk to the backend without moving retrieval or citation logic
into the frontend.

Notes:

- Open WebUI persists configuration in its data volume.
- If you change OpenAI connection settings and need a clean reset, remove the
  `open-webui-data` volume and recreate the stack.
