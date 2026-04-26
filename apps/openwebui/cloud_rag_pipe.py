from __future__ import annotations

import httpx
from pydantic import BaseModel, Field


class Pipe:
    class Valves(BaseModel):
        MODEL_ID: str = Field(default="cloud-rag-secure")
        MODEL_NAME: str = Field(default="Cloud RAG Secure")
        RAG_API_BASE_URL: str = Field(default="http://rag-api:8080")
        RAG_API_KEY: str = Field(default="")
        DEFAULT_TENANT_ID: str = Field(default="local-tenant")
        DEFAULT_ACL_TAGS: str = Field(default="public,employees")
        FORWARD_USER_TOKEN: bool = Field(default=True)
        TOP_K: int = Field(default=5, ge=1, le=20)
        TIMEOUT_SECONDS: float = Field(default=60.0, ge=1.0)

    def __init__(self) -> None:
        self.valves = self.Valves()

    async def pipes(self) -> list[dict[str, str]]:
        return [{"id": self.valves.MODEL_ID, "name": self.valves.MODEL_NAME}]

    async def pipe(self, body: dict, __user__: dict | None = None) -> str:
        user_message = _last_user_message(body)
        if not user_message:
            return "No user question was provided."

        user = __user__ or {}
        payload = {
            "question": user_message,
            "top_k": self.valves.TOP_K,
            "user_context": {
                "user_id": str(user.get("id") or "openwebui-user"),
                "email": str(user.get("email") or user.get("name") or "unknown@example.com"),
                "tenant_id": self.valves.DEFAULT_TENANT_ID,
                "acl_tags": _split_csv(self.valves.DEFAULT_ACL_TAGS),
            },
        }
        headers = {"Content-Type": "application/json"}
        user_token = _user_token(user) if self.valves.FORWARD_USER_TOKEN else None
        if user_token:
            headers["Authorization"] = f"Bearer {user_token}"
        elif self.valves.RAG_API_KEY:
            headers["Authorization"] = f"Bearer {self.valves.RAG_API_KEY}"

        url = f"{self.valves.RAG_API_BASE_URL.rstrip('/')}/api/v1/answer"
        async with httpx.AsyncClient(timeout=self.valves.TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()

        citations = result.get("citations") or []
        if not citations:
            return result.get("answer") or "No answer was returned."

        citation_lines = [
            f"[{citation['index']}] {citation['title']} - {citation['source_url']}"
            for citation in citations
        ]
        return f"{result.get('answer', '')}\n\nSources:\n" + "\n".join(citation_lines)


def _last_user_message(body: dict) -> str | None:
    messages = body.get("messages") or []
    for message in reversed(messages):
        if message.get("role") == "user" and message.get("content"):
            return str(message["content"])
    return None


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _user_token(user: dict) -> str | None:
    for key in ("access_token", "id_token", "oauth_token", "token"):
        value = user.get(key)
        if value:
            return str(value)
    return None
