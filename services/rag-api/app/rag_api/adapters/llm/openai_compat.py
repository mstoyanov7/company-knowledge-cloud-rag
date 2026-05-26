from __future__ import annotations

import hashlib
import json
import re

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
                answer_text="I could not find that information in the available OneNote notes.",
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

    async def plan_queries(
        self,
        *,
        question: str,
        detected_language: str,
        answer_type: str,
        important_entities: list[str],
        key_phrases: list[str],
        keyword_queries: list[str],
        must_have_concepts: list[str],
        avoid_concepts: list[str],
        expected_evidence_type: str,
    ) -> dict:
        response = await self._request(
            "POST",
            "/chat/completions",
            json={
                "model": self.model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You generate retrieval query plans for a OneNote RAG system. "
                            "Use only the user question and generic language understanding. "
                            "Do not use company-specific facts, OneNote content, memory, or outside knowledge. "
                            "Return only valid JSON."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "task": "Create search queries for retrieval, not an answer.",
                                "required_json_keys": [
                                    "original_question",
                                    "rewritten_question",
                                    "answer_type",
                                    "key_entities",
                                    "key_phrases",
                                    "semantic_queries",
                                    "keyword_queries",
                                    "must_have_concepts",
                                    "avoid_concepts",
                                ],
                                "question": question,
                                "detected_language": detected_language,
                                "answer_type": answer_type,
                                "key_entities": important_entities,
                                "key_phrases": key_phrases,
                                "keyword_queries": keyword_queries,
                                "must_have_concepts": must_have_concepts,
                                "avoid_concepts": avoid_concepts,
                                "expected_evidence_type": expected_evidence_type,
                                "rules": [
                                    "Base every query only on the user question.",
                                    "Preserve the user's main entity or concept in most generated queries.",
                                    "Preserve multi-word noun or verb phrases. Do not reduce strong phrases to one weak word.",
                                    "Include exact keywords and reasonable semantic paraphrases.",
                                    "Avoid over-broad one-word queries such as paid, date, policy, information, details, or notes.",
                                    "Put required concepts that retrieved evidence should contain in must_have_concepts.",
                                    "Put concepts that would indicate a different topic in avoid_concepts only when the user question implies them.",
                                    "Do not assume the answer.",
                                    "Do not include explanations outside JSON.",
                                ],
                            }
                        ),
                    },
                ],
                "temperature": 0.0,
                "max_tokens": 500,
                "stream": False,
            },
        )
        content = response.json()["choices"][0]["message"]["content"]
        return _parse_json_object(content)

    async def grade_relevance(
        self,
        *,
        question: str,
        question_analysis: dict[str, object],
        chunks: list[dict[str, object]],
    ) -> dict:
        response = await self._request(
            "POST",
            "/chat/completions",
            json={
                "model": self.model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You grade whether retrieved OneNote chunks answer the user's question. "
                            "Return only valid JSON. Do not answer the question. Do not reveal chain-of-thought."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "question": question,
                                "question_analysis": question_analysis,
                                "chunks": chunks,
                                "required_json_schema": {
                                    "chunks": [
                                        {
                                            "chunk_id": "string",
                                            "relevance": "direct | partial | related | irrelevant",
                                            "answers_question": True,
                                            "reason": "short reason, no chain of thought",
                                            "confidence": 0.0,
                                        }
                                    ]
                                },
                                "rules": [
                                    "direct means the chunk answers the specific question.",
                                    "partial means the chunk contains useful evidence but misses part of the requested answer.",
                                    "related means it shares topic words but does not answer.",
                                    "irrelevant means it is a different topic.",
                                    "A shared weak keyword alone is not direct evidence.",
                                    "Prefer title plus content together when deciding relevance.",
                                ],
                            }
                        ),
                    },
                ],
                "temperature": 0.0,
                "max_tokens": 700,
                "stream": False,
            },
        )
        content = response.json()["choices"][0]["message"]["content"]
        return _parse_json_object(content)

    def _messages(self, prompt: PromptContext) -> list[dict[str, str]]:
        context = "\n\n".join(prompt.context_blocks)
        question_analysis = _format_question_analysis(prompt.question_analysis)
        source_titles = ", ".join(prompt.source_titles)
        request_fingerprint = hashlib.sha256(
            f"{prompt.user_question}\n{context}".encode("utf-8")
        ).hexdigest()[:12]
        user_content = (
            f"Independent request id: {request_fingerprint}\n"
            "This is a new independent retrieval request. Ignore any prior answer text from the chat UI. "
            "Do not repeat a previous answer unless the current question asks for the same information.\n\n"
            f"Current user question to answer now:\n{prompt.user_question}\n\n"
            f"Internal question analysis, for retrieval interpretation only:\n{question_analysis}\n\n"
            f"Retrieved context:\n{context}\n\n"
            "Use only the retrieved OneNote context above. "
            "Do not use any outside knowledge. "
            "Answer only the current user question, not a different topic from the context. "
            "Think silently about what the user means, but do not show hidden reasoning or chain-of-thought. "
            "Do not answer by copying only the first keyword-matching sentence. "
            "Use the context to create a clear, descriptive answer that explains the relevant details. "
            "Answer naturally and politely, like a helpful human assistant. "
            "Return clean Markdown. Use a short heading and bullets for structured facts. "
            "For key-value lines, preserve source labels as bold bullet labels. "
            "Do not add facts from loosely related chunks. "
            "Do not include numeric citation markers like [1], [2], or source IDs. "
            f"If you answer with facts, end with an italic Sources line using only these page titles: {source_titles}. "
            "If the context is related but does not directly answer the question, reply exactly: "
            "I could not find that information in the available OneNote notes. "
            "If the context does not answer the question, reply exactly: "
            "I could not find that information in the available OneNote notes."
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


def _format_question_analysis(question_analysis: dict[str, object] | None) -> str:
    if not question_analysis:
        return "N/A"
    lines = []
    for key in (
        "detected_language",
        "answer_type",
        "important_entities",
        "key_phrases",
        "rewritten_question",
        "expected_evidence_type",
        "must_have_concepts",
        "avoid_concepts",
        "specificity",
    ):
        value = question_analysis.get(key)
        if value in (None, "", []):
            continue
        lines.append(f"- {key}: {value}")
    return "\n".join(lines) if lines else "N/A"


def _parse_json_object(value: str) -> dict:
    stripped = value.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}
