from __future__ import annotations

import asyncio
import json

import httpx
from rag_api.adapters.llm.openai_compat import OpenAICompatibleLlmAdapter
from rag_api.ports import PromptContext
from rag_api.services.prompt_builder import PromptBuilder
from shared_schemas import AppSettings, ChunkDocument, Citation

NO_INFORMATION_ANSWER = "I could not find that information in the available OneNote notes or readable attachments."


def test_openai_compatible_llm_calls_chat_completions() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "gpt-oss:120b-cloud"}]})
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "gpt-oss:120b-cloud"
        assert body["messages"][0]["role"] == "system"
        assert "Do not use outside knowledge" in body["messages"][0]["content"]
        assert "Retrieved context" in body["messages"][1]["content"]
        assert "This is a new independent retrieval request" in body["messages"][1]["content"]
        assert "Current user question to answer now" in body["messages"][1]["content"]
        assert f"reply exactly: {NO_INFORMATION_ANSWER}" in body["messages"][1]["content"]
        assert "Internal question analysis" in body["messages"][1]["content"]
        assert "Do not include numeric citation markers" in body["messages"][1]["content"]
        return httpx.Response(
            200,
            json={
                "model": "gpt-oss:120b-cloud",
                "choices": [{"message": {"content": "Use VPN setup from the notes. [1]"}}],
            },
        )

    async def run() -> None:
        settings = AppSettings(
            app_env="test",
            default_llm_provider="ollama",
            default_model_name="gpt-oss:120b-cloud",
            llm_openai_base_url="http://ollama.test/v1",
            security_audit_enabled=False,
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OpenAICompatibleLlmAdapter(settings, http_client=client)
            citation = Citation(
                index=1,
                chunk_id="c1",
                source_item_id="s1",
                chunk_index=0,
                title="Setup",
                source_system="onenote",
                source_container="onenote",
                source_url="https://example.test",
                snippet="Configure VPN access.",
                last_modified_utc="2026-04-26T00:00:00Z",
            )
            chunk = ChunkDocument(
                tenant_id="local-tenant",
                source_system="onenote",
                source_container="onenote",
                source_item_id="s1",
                source_url="https://example.test",
                title="Setup",
                content_hash="hash",
                chunk_id="c1",
                chunk_index=0,
                chunk_text="Configure VPN access.",
                embedding_model="token-hash-v1",
            )
            prompt = PromptBuilder().build("What should I set up?", [chunk], [citation])
            result = await adapter.generate(prompt)
            assert result.answer_text == "Use VPN setup from the notes. [1]"
            assert await adapter.ready() is True
            assert await adapter.list_models() == ["gpt-oss:120b-cloud"]

    asyncio.run(run())
    assert [request.url.path for request in requests] == [
        "/v1/chat/completions",
        "/v1/models",
        "/v1/models",
    ]


def test_openai_compatible_llm_returns_no_information_without_citations() -> None:
    async def run() -> None:
        settings = AppSettings(
            app_env="test",
            default_llm_provider="ollama",
            default_model_name="gpt-oss:120b-cloud",
            security_audit_enabled=False,
        )
        adapter = OpenAICompatibleLlmAdapter(settings)
        result = await adapter.generate(
            PromptContext(
                system_instruction="Answer from context.",
                user_question="What is the vacation policy?",
                context_blocks=[],
                citations=[],
            )
        )
        assert result.answer_text == NO_INFORMATION_ANSWER

    asyncio.run(run())
