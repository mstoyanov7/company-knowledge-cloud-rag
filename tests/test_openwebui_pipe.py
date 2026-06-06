from __future__ import annotations

import asyncio

from apps.openwebui.cloud_rag_pipe import Pipe

NO_INFORMATION_ANSWER = "I could not find that information in the available OneNote notes or readable attachments."


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeAsyncClient:
    requests: list[dict] = []
    payload: dict = {}

    def __init__(self, *args, **kwargs) -> None:
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, *, json: dict, headers: dict):
        self.requests.append({"url": url, "json": json, "headers": headers})
        return FakeResponse(self.payload)


def test_openwebui_pipe_forces_onenote_sources_and_no_information(monkeypatch) -> None:
    from apps.openwebui import cloud_rag_pipe

    FakeAsyncClient.requests = []
    FakeAsyncClient.payload = {"answer": "General internet answer", "citations": []}
    monkeypatch.setattr(cloud_rag_pipe.httpx, "AsyncClient", FakeAsyncClient)

    pipe = Pipe()
    pipe.valves.RAG_API_KEY = "test-key"
    result = asyncio.run(
        pipe.pipe(
            {
                "messages": [
                    {"role": "user", "content": "What is the capital of France?"}
                ]
            }
        )
    )

    assert result == NO_INFORMATION_ANSWER
    assert FakeAsyncClient.requests[0]["json"]["source_filters"] == ["onenote"]


def test_openwebui_pipe_returns_answer_with_title_sources_without_numeric_markers(monkeypatch) -> None:
    from apps.openwebui import cloud_rag_pipe

    FakeAsyncClient.requests = []
    FakeAsyncClient.payload = {
        "answer": "### Remote Work Policy\n\n- Allowed up to 3 days per week",
        "citations": [
            {
                "index": 1,
                "title": "Remote Work Policy",
                "source_url": "https://example.test/remote-work",
            }
        ],
    }
    monkeypatch.setattr(cloud_rag_pipe.httpx, "AsyncClient", FakeAsyncClient)

    pipe = Pipe()
    pipe.valves.RAG_API_KEY = "test-key"
    result = asyncio.run(
        pipe.pipe(
            {
                "messages": [
                    {"role": "user", "content": "What is the remote work policy?"}
                ]
            }
        )
    )

    assert "[1]" not in result
    assert "https://example.test/remote-work" not in result
    assert result == "### Remote Work Policy\n\n- Allowed up to 3 days per week"
