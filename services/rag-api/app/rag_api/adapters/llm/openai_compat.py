from __future__ import annotations

import httpx
from shared_schemas import AppSettings

from rag_api.ports import GenerationResult, PromptContext


class OpenAICompatibleLlmAdapter:
    provider_name = "openai-compatible"

    def __init__(self, settings: AppSettings, *, http_client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.model_name = settings.default_model_name
        self.base_url = settings.llm_openai_base_url.rstrip("/")
        self.api_key = settings.llm_openai_api_key.get_secret_value()
        self.http_client = http_client

    async def generate(self, prompt: PromptContext) -> GenerationResult:
        if not prompt.citations:
            return GenerationResult(
                provider=self.provider_name,
                model=self.model_name,
                answer_text="No information",
            )

        response = await self._request(
            "POST",
            "/chat/completions",
            json={
                "model": self.model_name,
                "messages": self._messages(prompt),
                "temperature": self.settings.llm_temperature,
                "max_tokens": self.settings.llm_max_tokens,
                "stream": False,
            },
        )
        payload = response.json()
        answer_text = payload["choices"][0]["message"]["content"].strip()
        return GenerationResult(
            provider=self.provider_name,
            model=str(payload.get("model") or self.model_name),
            answer_text=answer_text,
        )

    async def ready(self) -> bool:
        try:
            await self._request("GET", "/models")
        except Exception:
            return False
        return True

    async def list_models(self) -> list[str]:
        response = await self._request("GET", "/models")
        payload = response.json()
        return [str(model["id"]) for model in payload.get("data", []) if model.get("id")]

    def _messages(self, prompt: PromptContext) -> list[dict[str, str]]:
        context = "\n\n".join(prompt.context_blocks)
        user_content = (
            f"Question:\n{prompt.user_question}\n\n"
            f"Retrieved context:\n{context}\n\n"
            "Use only the retrieved OneNote context above. "
            "Do not use any outside knowledge. "
            "Answer the specific question, not a different topic from the context. "
            "Do not answer by copying only the first keyword-matching sentence. "
            "Use the context to create a clear, descriptive answer that explains the relevant details. "
            "Return clean Markdown. Use a short heading and bullets for structured facts. "
            "For key-value lines, preserve source labels as bold bullet labels. "
            "Do not add facts from loosely related chunks and do not add a separate sources section. "
            "Include citation markers like [1] for every factual claim. "
            "If the context is related but does not directly answer the question, reply exactly: No information. "
            "If the context does not answer the question, reply exactly: No information"
        )
        return [
            {"role": "system", "content": prompt.system_instruction},
            {"role": "user", "content": user_content},
        ]

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers.setdefault("Authorization", f"Bearer {self.api_key}")
        headers.setdefault("Content-Type", "application/json")
        headers.setdefault("Accept", "application/json")
        url = f"{self.base_url}/{path.lstrip('/')}"

        if self.http_client is not None:
            response = await self.http_client.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            return response

        async with httpx.AsyncClient(timeout=self.settings.llm_request_timeout_seconds) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            return response
