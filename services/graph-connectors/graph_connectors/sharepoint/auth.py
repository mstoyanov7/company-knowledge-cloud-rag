from __future__ import annotations

import time

import httpx
from shared_schemas import AppSettings


class ClientCredentialsTokenProvider:
    def __init__(self, settings: AppSettings, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.http_client = http_client or httpx.Client(timeout=30.0)
        self._access_token: str | None = None
        self._expires_at_epoch: float = 0.0

    def get_access_token(self) -> str:
        if self._access_token and time.time() < self._expires_at_epoch - 60:
            return self._access_token

        response = self.http_client.post(
            f"https://login.microsoftonline.com/{self.settings.graph_tenant_id}/oauth2/v2.0/token",
            data={
                "client_id": self.settings.graph_client_id,
                "client_secret": self.settings.graph_client_secret.get_secret_value(),
                "scope": self.settings.graph_token_scope,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        payload = response.json()
        self._access_token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 3600))
        self._expires_at_epoch = time.time() + expires_in
        return self._access_token
