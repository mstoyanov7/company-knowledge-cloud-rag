from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rag_api.dependencies import get_graph_webhook_service
from rag_api.main import create_app
from rag_api.services.graph_webhook_service import GraphWebhookService, InvalidGraphNotificationError
from shared_schemas import AppSettings, GraphNotificationEnvelope, GraphWebhookAccepted, OpsJobType
from sync_worker.persistence.ops_store import compute_backoff_seconds


class FakeWebhookStore:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.jobs: list[dict] = []
        self.reauthorization_required: list[str] = []
        self.removed: list[str] = []
        self.duplicates: set[str] = set()

    def record_webhook_event(self, *, dedupe_key, subscription_id, event_type, resource, payload) -> bool:
        if dedupe_key in self.duplicates:
            return False
        self.duplicates.add(dedupe_key)
        self.events.append(
            {
                "dedupe_key": dedupe_key,
                "subscription_id": subscription_id,
                "event_type": event_type,
                "resource": resource,
                "payload": payload,
            }
        )
        return True

    def enqueue_job(self, job_type, payload=None, *, dedupe_key=None, max_attempts=None):
        self.jobs.append(
            {
                "job_type": job_type,
                "payload": payload or {},
                "dedupe_key": dedupe_key,
                "max_attempts": max_attempts,
            }
        )
        return None, True

    def mark_subscription_reauthorization_required(self, subscription_id: str) -> None:
        self.reauthorization_required.append(subscription_id)

    def mark_subscription_removed(self, subscription_id: str) -> None:
        self.removed.append(subscription_id)


def test_graph_webhook_validation_token_returns_decoded_plain_text() -> None:
    settings = AppSettings(app_env="test")
    app = create_app(settings)
    app.dependency_overrides[get_graph_webhook_service] = lambda: GraphWebhookService(
        settings=settings,
        store=FakeWebhookStore(),
    )
    client = TestClient(app)

    response = client.post("/api/v1/graph/notifications?validationToken=opaque%3Aabc%2B123")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "opaque:abc+123"


def test_graph_webhook_accepts_valid_notification_and_enqueues_catchup() -> None:
    settings = AppSettings(app_env="test", graph_subscription_client_state="secret-state")
    store = FakeWebhookStore()
    service = GraphWebhookService(settings=settings, store=store)
    envelope = GraphNotificationEnvelope.model_validate(
        {
            "value": [
                {
                    "subscriptionId": "sub-1",
                    "clientState": "secret-state",
                    "changeType": "updated",
                    "resource": "drives/drive-1/root",
                    "resourceData": {"id": "item-1"},
                }
            ]
        }
    )

    result = service.accept(envelope)

    assert result == GraphWebhookAccepted(notification_count=1, enqueued_count=1)
    assert store.events[0]["event_type"] == "change"
    assert store.jobs[0]["job_type"] == OpsJobType.sharepoint_delta_catchup.value
    assert store.jobs[0]["payload"]["resource"] == "drives/drive-1/root"


def test_graph_webhook_rejects_invalid_client_state() -> None:
    settings = AppSettings(app_env="test", graph_subscription_client_state="secret-state")
    service = GraphWebhookService(settings=settings, store=FakeWebhookStore())
    envelope = GraphNotificationEnvelope.model_validate(
        {"value": [{"subscriptionId": "sub-1", "clientState": "wrong", "resource": "drives/drive-1/root"}]}
    )

    with pytest.raises(InvalidGraphNotificationError):
        service.accept(envelope)


def test_graph_lifecycle_reauthorization_enqueues_reauthorize_job() -> None:
    settings = AppSettings(app_env="test", graph_subscription_client_state="secret-state")
    store = FakeWebhookStore()
    service = GraphWebhookService(settings=settings, store=store)
    envelope = GraphNotificationEnvelope.model_validate(
        {
            "value": [
                {
                    "subscriptionId": "sub-1",
                    "clientState": "secret-state",
                    "lifecycleEvent": "reauthorizationRequired",
                }
            ]
        }
    )

    result = service.accept(envelope)

    assert result.lifecycle_count == 1
    assert store.reauthorization_required == ["sub-1"]
    assert store.jobs[0]["job_type"] == OpsJobType.graph_subscription_reauthorize.value


def test_ops_backoff_caps_exponential_delay() -> None:
    assert compute_backoff_seconds(attempt=1, base_seconds=30, max_seconds=1800) == 30
    assert compute_backoff_seconds(attempt=3, base_seconds=30, max_seconds=1800) == 120
    assert compute_backoff_seconds(attempt=10, base_seconds=30, max_seconds=1800) == 1800
