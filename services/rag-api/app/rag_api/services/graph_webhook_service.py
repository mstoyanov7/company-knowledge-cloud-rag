from __future__ import annotations

import hashlib
import json
import logging
import secrets
from typing import Protocol

from shared_schemas import (
    AppSettings,
    GraphChangeNotification,
    GraphLifecycleEvent,
    GraphNotificationEnvelope,
    GraphWebhookAccepted,
    OpsJobType,
)


class GraphWebhookStorePort(Protocol):
    def record_webhook_event(
        self,
        *,
        dedupe_key: str,
        subscription_id: str | None,
        event_type: str,
        resource: str | None,
        payload: dict,
    ) -> bool:
        raise NotImplementedError

    def enqueue_job(
        self,
        job_type: str,
        payload: dict | None = None,
        *,
        dedupe_key: str | None = None,
        max_attempts: int | None = None,
    ):
        raise NotImplementedError

    def mark_subscription_reauthorization_required(self, subscription_id: str) -> None:
        raise NotImplementedError

    def mark_subscription_removed(self, subscription_id: str) -> None:
        raise NotImplementedError


class InvalidGraphNotificationError(ValueError):
    pass


class GraphWebhookService:
    def __init__(
        self,
        *,
        settings: AppSettings,
        store: GraphWebhookStorePort,
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.logger = logger or logging.getLogger("rag_api.graph_webhook")

    def accept(self, envelope: GraphNotificationEnvelope) -> GraphWebhookAccepted:
        expected_client_state = self.settings.graph_subscription_client_state.get_secret_value()
        accepted = GraphWebhookAccepted(notification_count=len(envelope.value))

        for notification in envelope.value:
            self._validate_client_state(notification, expected_client_state)
            event_type = notification.lifecycle_event.value if notification.lifecycle_event else "change"
            payload = notification.model_dump(mode="json", by_alias=True, exclude_none=True)
            event_dedupe_key = self._event_dedupe_key(notification, payload)
            created = self.store.record_webhook_event(
                dedupe_key=event_dedupe_key,
                subscription_id=notification.subscription_id,
                event_type=event_type,
                resource=notification.resource,
                payload=payload,
            )
            if not created:
                accepted.duplicate_count += 1
                self.logger.info(
                    "event=graph_webhook_duplicate subscription_id=%s event_type=%s resource=%s",
                    notification.subscription_id,
                    event_type,
                    notification.resource,
                )
                continue

            enqueued = self._enqueue_followup(notification, payload, event_dedupe_key)
            accepted.enqueued_count += enqueued
            if notification.lifecycle_event:
                accepted.lifecycle_count += 1

        self.logger.info(
            "event=graph_webhook_accepted notifications=%s enqueued=%s duplicates=%s lifecycle=%s",
            accepted.notification_count,
            accepted.enqueued_count,
            accepted.duplicate_count,
            accepted.lifecycle_count,
        )
        return accepted

    def _validate_client_state(self, notification: GraphChangeNotification, expected_client_state: str) -> None:
        if not notification.client_state:
            raise InvalidGraphNotificationError("Missing Microsoft Graph clientState.")
        if not secrets.compare_digest(notification.client_state, expected_client_state):
            raise InvalidGraphNotificationError("Invalid Microsoft Graph clientState.")

    def _enqueue_followup(
        self,
        notification: GraphChangeNotification,
        payload: dict,
        event_dedupe_key: str,
    ) -> int:
        if notification.lifecycle_event == GraphLifecycleEvent.reauthorization_required:
            self.store.mark_subscription_reauthorization_required(notification.subscription_id)
            self.store.enqueue_job(
                OpsJobType.graph_subscription_reauthorize.value,
                {"subscription_id": notification.subscription_id, "notification": payload},
                dedupe_key=f"graph_subscription_reauthorize:{event_dedupe_key}",
                max_attempts=self.settings.ops_job_max_attempts,
            )
            return 1

        if notification.lifecycle_event == GraphLifecycleEvent.subscription_removed:
            self.store.mark_subscription_removed(notification.subscription_id)
            self.store.enqueue_job(
                OpsJobType.sharepoint_subscription_ensure.value,
                {"subscription_id": notification.subscription_id, "notification": payload},
                dedupe_key=f"sharepoint_subscription_ensure:{event_dedupe_key}",
                max_attempts=self.settings.ops_job_max_attempts,
            )
            self.store.enqueue_job(
                OpsJobType.sharepoint_delta_catchup.value,
                {"subscription_id": notification.subscription_id, "notification": payload},
                dedupe_key=f"sharepoint_delta_catchup:{event_dedupe_key}",
                max_attempts=self.settings.ops_job_max_attempts,
            )
            return 2

        if notification.lifecycle_event == GraphLifecycleEvent.missed:
            self.store.enqueue_job(
                OpsJobType.sharepoint_delta_catchup.value,
                {"subscription_id": notification.subscription_id, "notification": payload, "reason": "missed"},
                dedupe_key=f"sharepoint_delta_catchup:{event_dedupe_key}",
                max_attempts=self.settings.ops_job_max_attempts,
            )
            return 1

        self.store.enqueue_job(
            OpsJobType.sharepoint_delta_catchup.value,
            {
                "subscription_id": notification.subscription_id,
                "change_type": notification.change_type,
                "resource": notification.resource,
                "resource_data": payload.get("resourceData"),
            },
            dedupe_key=f"sharepoint_delta_catchup:{event_dedupe_key}",
            max_attempts=self.settings.ops_job_max_attempts,
        )
        return 1

    @staticmethod
    def _event_dedupe_key(notification: GraphChangeNotification, payload: dict) -> str:
        stable = {
            "subscription_id": notification.subscription_id,
            "change_type": notification.change_type,
            "resource": notification.resource,
            "resource_data": payload.get("resourceData"),
            "lifecycle_event": notification.lifecycle_event.value if notification.lifecycle_event else None,
        }
        raw = json.dumps(stable, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
