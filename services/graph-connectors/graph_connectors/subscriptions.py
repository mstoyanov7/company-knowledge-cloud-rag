from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx
from shared_schemas import AppSettings, GraphSubscriptionRecord

from graph_connectors.sharepoint.auth import ClientCredentialsTokenProvider


class GraphSubscriptionClient(ABC):
    @abstractmethod
    def create_subscription(
        self,
        *,
        resource: str,
        change_type: str,
        notification_url: str,
        lifecycle_notification_url: str | None,
        client_state: str,
        expiration_datetime_utc: datetime,
    ) -> GraphSubscriptionRecord:
        raise NotImplementedError

    @abstractmethod
    def renew_subscription(
        self,
        *,
        subscription_id: str,
        expiration_datetime_utc: datetime,
    ) -> GraphSubscriptionRecord:
        raise NotImplementedError

    @abstractmethod
    def reauthorize_subscription(self, subscription_id: str) -> None:
        raise NotImplementedError


class MicrosoftGraphSubscriptionClient(GraphSubscriptionClient):
    def __init__(
        self,
        settings: AppSettings,
        *,
        token_provider: ClientCredentialsTokenProvider | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self.token_provider = token_provider or ClientCredentialsTokenProvider(settings)
        self.http_client = http_client or httpx.Client(timeout=30.0)

    def create_subscription(
        self,
        *,
        resource: str,
        change_type: str,
        notification_url: str,
        lifecycle_notification_url: str | None,
        client_state: str,
        expiration_datetime_utc: datetime,
    ) -> GraphSubscriptionRecord:
        payload = {
            "changeType": change_type,
            "notificationUrl": notification_url,
            "resource": resource,
            "expirationDateTime": _format_graph_datetime(expiration_datetime_utc),
            "clientState": client_state,
        }
        if lifecycle_notification_url:
            payload["lifecycleNotificationUrl"] = lifecycle_notification_url
        response = self._request_json("POST", "/subscriptions", json=payload)
        return _subscription_from_payload(
            response,
            fallback_client_state=client_state,
            fallback_lifecycle_url=lifecycle_notification_url,
        )

    def renew_subscription(
        self,
        *,
        subscription_id: str,
        expiration_datetime_utc: datetime,
    ) -> GraphSubscriptionRecord:
        response = self._request_json(
            "PATCH",
            f"/subscriptions/{subscription_id}",
            json={"expirationDateTime": _format_graph_datetime(expiration_datetime_utc)},
        )
        return _subscription_from_payload(response, fallback_client_state="", fallback_lifecycle_url=None)

    def reauthorize_subscription(self, subscription_id: str) -> None:
        response = self.http_client.post(
            _graph_url(self.settings.graph_api_base_url, f"/subscriptions/{subscription_id}/reauthorize"),
            headers=self._headers(),
        )
        response.raise_for_status()

    def _request_json(self, method: str, path: str, *, json: dict[str, Any]) -> dict[str, Any]:
        response = self.http_client.request(
            method,
            _graph_url(self.settings.graph_api_base_url, path),
            headers=self._headers(),
            json=json,
        )
        response.raise_for_status()
        return response.json()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token_provider.get_access_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }


class MockGraphSubscriptionClient(GraphSubscriptionClient):
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._subscriptions: dict[str, GraphSubscriptionRecord] = {}

    def create_subscription(
        self,
        *,
        resource: str,
        change_type: str,
        notification_url: str,
        lifecycle_notification_url: str | None,
        client_state: str,
        expiration_datetime_utc: datetime,
    ) -> GraphSubscriptionRecord:
        subscription_id = f"mock-subscription-{uuid5(NAMESPACE_URL, resource)}"
        record = GraphSubscriptionRecord(
            subscription_id=subscription_id,
            resource=resource,
            change_type=change_type,
            notification_url=notification_url,
            lifecycle_notification_url=lifecycle_notification_url,
            client_state=client_state,
            expiration_datetime_utc=expiration_datetime_utc,
            metadata={"mode": "mock"},
        )
        self._subscriptions[subscription_id] = record
        return record

    def renew_subscription(
        self,
        *,
        subscription_id: str,
        expiration_datetime_utc: datetime,
    ) -> GraphSubscriptionRecord:
        existing = self._subscriptions.get(subscription_id)
        if existing is None:
            existing = GraphSubscriptionRecord(
                subscription_id=subscription_id,
                resource=self.settings.graph_sharepoint_subscription_resource or "drives/mock-drive-documents/root",
                change_type=self.settings.graph_sharepoint_subscription_change_type,
                notification_url=self.settings.graph_notification_url or "https://example.invalid/api/v1/graph/notifications",
                lifecycle_notification_url=self.settings.graph_lifecycle_notification_url
                or "https://example.invalid/api/v1/graph/lifecycle",
                client_state=self.settings.graph_subscription_client_state.get_secret_value(),
                expiration_datetime_utc=expiration_datetime_utc,
                metadata={"mode": "mock", "renewed_without_local_create": True},
            )
        renewed = existing.model_copy(
            update={
                "expiration_datetime_utc": expiration_datetime_utc,
                "reauthorization_required": False,
            }
        )
        self._subscriptions[subscription_id] = renewed
        return renewed

    def reauthorize_subscription(self, subscription_id: str) -> None:
        return None


def build_graph_subscription_client(settings: AppSettings) -> GraphSubscriptionClient:
    if settings.sharepoint_graph_mode == "live":
        return MicrosoftGraphSubscriptionClient(settings)
    return MockGraphSubscriptionClient(settings)


def _subscription_from_payload(
    payload: dict[str, Any],
    *,
    fallback_client_state: str,
    fallback_lifecycle_url: str | None,
) -> GraphSubscriptionRecord:
    return GraphSubscriptionRecord(
        subscription_id=payload["id"],
        resource=payload["resource"],
        change_type=payload["changeType"],
        notification_url=payload["notificationUrl"],
        lifecycle_notification_url=payload.get("lifecycleNotificationUrl") or fallback_lifecycle_url,
        client_state=payload.get("clientState") or fallback_client_state,
        expiration_datetime_utc=_parse_graph_datetime(payload["expirationDateTime"]),
        metadata={"raw_subscription": payload},
    )


def _format_graph_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_graph_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _graph_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"
