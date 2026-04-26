from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from graph_connectors import SharePointConnector, build_graph_subscription_client
from graph_connectors.subscriptions import GraphSubscriptionClient
from shared_schemas import AppSettings, GraphSubscriptionRecord, GraphSubscriptionStatus

from sync_worker.persistence import PostgresOpsStore


class GraphSubscriptionMaintenanceService:
    def __init__(
        self,
        settings: AppSettings,
        *,
        store: PostgresOpsStore | None = None,
        client: GraphSubscriptionClient | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings = settings
        self.store = store or PostgresOpsStore(settings)
        self.client = client or build_graph_subscription_client(settings)
        self.logger = logger or logging.getLogger("sync_worker.ops.subscriptions")

    def ensure_sharepoint_subscription(self) -> GraphSubscriptionRecord | None:
        self.store.ensure_schema()
        notification_url = self.settings.graph_notification_url
        lifecycle_url = self.settings.graph_lifecycle_notification_url
        if not notification_url or not lifecycle_url:
            self.logger.warning(
                "event=graph_subscription_skipped reason=missing_public_notification_url notification_url=%s lifecycle_url=%s",
                notification_url,
                lifecycle_url,
            )
            return None
        if self.settings.sharepoint_graph_mode == "live" and not notification_url.startswith("https://"):
            raise ValueError("GRAPH_NOTIFICATION_BASE_URL must be HTTPS for live Microsoft Graph subscriptions.")

        resource = self._sharepoint_subscription_resource()
        expiration = self._next_expiration()
        record = self.client.create_subscription(
            resource=resource,
            change_type=self.settings.graph_sharepoint_subscription_change_type,
            notification_url=notification_url,
            lifecycle_notification_url=lifecycle_url,
            client_state=self.settings.graph_subscription_client_state.get_secret_value(),
            expiration_datetime_utc=expiration,
        )
        record = record.model_copy(
            update={
                "status": GraphSubscriptionStatus.active,
                "reauthorization_required": False,
                "last_successful_renewal_utc": datetime.now(UTC),
            }
        )
        self.store.upsert_subscription(record)
        self.logger.info(
            "event=graph_subscription_ensured subscription_id=%s resource=%s expires=%s",
            record.subscription_id,
            record.resource,
            record.expiration_datetime_utc.isoformat(),
        )
        return record

    def renew_due_subscriptions(self) -> int:
        self.store.ensure_schema()
        due = self.store.list_subscriptions_due_for_renewal(self.settings.graph_subscription_renewal_window_minutes)
        renewed = 0
        for subscription in due:
            try:
                self.store.mark_subscription_renewal_attempt(subscription.subscription_id)
                record = self.client.renew_subscription(
                    subscription_id=subscription.subscription_id,
                    expiration_datetime_utc=self._next_expiration(),
                )
                record = subscription.model_copy(
                    update={
                        "expiration_datetime_utc": record.expiration_datetime_utc,
                        "status": GraphSubscriptionStatus.active,
                        "reauthorization_required": False,
                        "last_renewal_attempt_utc": datetime.now(UTC),
                        "last_successful_renewal_utc": datetime.now(UTC),
                    }
                )
                self.store.upsert_subscription(record)
                renewed += 1
                self.logger.info(
                    "event=graph_subscription_renewed subscription_id=%s expires=%s",
                    subscription.subscription_id,
                    record.expiration_datetime_utc.isoformat(),
                )
            except Exception as error:
                self.store.mark_subscription_renewal_attempt(subscription.subscription_id, str(error))
                self.logger.exception(
                    "event=graph_subscription_renewal_failed subscription_id=%s",
                    subscription.subscription_id,
                )
                raise
        return renewed

    def reauthorize_subscription(self, subscription_id: str) -> None:
        self.client.reauthorize_subscription(subscription_id)
        self.store.mark_subscription_active(subscription_id)
        self.logger.info("event=graph_subscription_reauthorized subscription_id=%s", subscription_id)

    def _sharepoint_subscription_resource(self) -> str:
        if self.settings.graph_sharepoint_subscription_resource:
            return self.settings.graph_sharepoint_subscription_resource
        if self.settings.sharepoint_graph_mode != "live":
            return "drives/mock-drive-documents/root"
        _site, drive = SharePointConnector(self.settings).resolve_scope()
        return f"drives/{drive.id}/root"

    def _next_expiration(self) -> datetime:
        return datetime.now(UTC) + timedelta(minutes=self.settings.graph_subscription_max_expiration_minutes)
