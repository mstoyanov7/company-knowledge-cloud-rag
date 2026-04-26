from __future__ import annotations

import logging
from typing import Protocol

from shared_schemas import AppSettings, SecurityAuditEvent


class SecurityAuditStorePort(Protocol):
    def record_security_audit_event(self, event: SecurityAuditEvent) -> None:
        raise NotImplementedError


class SecurityAuditLogger:
    def __init__(
        self,
        settings: AppSettings,
        *,
        store: SecurityAuditStorePort | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.logger = logger or logging.getLogger("rag_api.security_audit")

    def record(
        self,
        event_type: str,
        outcome: str,
        *,
        actor_user_id: str | None = None,
        tenant_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        if not self.settings.security_audit_enabled:
            return
        event = SecurityAuditEvent(
            event_type=event_type,
            outcome=outcome,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=_sanitize_metadata(metadata or {}),
        )
        self.logger.info("security_audit=%s", event.model_dump_json(exclude_none=True))
        if self.store is None:
            return
        try:
            self.store.record_security_audit_event(event)
        except Exception:
            self.logger.exception("event=security_audit_persist_failed audit_event_type=%s", event_type)


def _sanitize_metadata(metadata: dict) -> dict:
    redacted_keys = {"authorization", "token", "access_token", "id_token", "client_secret", "password"}
    sanitized: dict = {}
    for key, value in metadata.items():
        if key.lower() in redacted_keys:
            sanitized[key] = "[redacted]"
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_metadata(value)
        else:
            sanitized[key] = value
    return sanitized
