from __future__ import annotations

import asyncio

from apps.openwebui.cloud_rag_pipe import Pipe


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

    assert result == "No information"
    assert FakeAsyncClient.requests[0]["json"]["source_filters"] == ["onenote"]
