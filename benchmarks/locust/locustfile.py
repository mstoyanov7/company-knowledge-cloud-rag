from __future__ import annotations

import json
import os
import random
from pathlib import Path

from locust import HttpUser, between, events, task


DATASET_PATH = Path(os.getenv("DATASET_PATH", "benchmarks/datasets/onboarding_questions.json"))
RAG_API_KEY = os.getenv("RAG_API_KEY", "")
BENCHMARK_RUN_ID = os.getenv("BENCHMARK_RUN_ID", "locust-local")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "60"))


def load_cases() -> list[dict]:
    payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    return payload["cases"]


CASES = load_cases()


class ChatUser(HttpUser):
    wait_time = between(
        float(os.getenv("LOCUST_MIN_WAIT_SECONDS", "0.5")),
        float(os.getenv("LOCUST_MAX_WAIT_SECONDS", "2.0")),
    )

    @task
    def ask_onboarding_question(self) -> None:
        benchmark_case = random.choice(CASES)
        payload = {
            "question": benchmark_case["question"],
            "user_context": benchmark_case["user_context"],
            "top_k": benchmark_case.get("top_k", 3),
        }
        headers = {
            "Content-Type": "application/json",
            "X-Benchmark-Run-Id": BENCHMARK_RUN_ID,
            "X-Benchmark-Case-Id": benchmark_case["case_id"],
        }
        if RAG_API_KEY:
            headers["Authorization"] = f"Bearer {RAG_API_KEY}"

        with self.client.post(
            "/api/v1/answer",
            json=payload,
            headers=headers,
            name="/api/v1/answer",
            timeout=REQUEST_TIMEOUT_SECONDS,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"unexpected status={response.status_code}")
                return

            try:
                body = response.json()
            except ValueError as error:
                response.failure(f"invalid json: {error}")
                return

            metadata = body.get("metadata") or {}
            if not body.get("answer"):
                response.failure("missing answer")
                return

            response.success()
            _record_metric("RAG", "answer_latency_ms", metadata.get("duration_ms", 0))
            _record_metric("RAG", "retrieval_latency_ms", metadata.get("retrieval_latency_ms", 0))
            _record_metric("RAG", "completion_latency_ms", metadata.get("completion_latency_ms", 0))
            _record_metric("RAG", "citation_count", metadata.get("citation_count", len(body.get("citations") or [])))
            if metadata.get("freshness_delay_ms") is not None:
                _record_metric("RAG", "freshness_delay_ms", metadata.get("freshness_delay_ms", 0))


def _record_metric(request_type: str, name: str, response_time: float) -> None:
    events.request.fire(
        request_type=request_type,
        name=name,
        response_time=float(response_time or 0),
        response_length=0,
        exception=None,
        context={},
    )
