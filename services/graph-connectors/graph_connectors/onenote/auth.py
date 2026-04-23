from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

import msal
from shared_schemas import AppSettings


class DelegatedAuthProvider(ABC):
    @abstractmethod
    def get_access_token(self) -> str:
        raise NotImplementedError


class MockOneNoteDelegatedAuthProvider(DelegatedAuthProvider):
    def get_access_token(self) -> str:
        return "mock-onenote-access-token"


class MsalDeviceCodeAuthProvider(DelegatedAuthProvider):
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.cache_path = Path(settings.onenote_token_cache_path)
        self.cache = msal.SerializableTokenCache()
        if self.cache_path.exists():
            self.cache.deserialize(self.cache_path.read_text(encoding="utf-8"))
        self.application = msal.PublicClientApplication(
            client_id=settings.graph_onenote_client_id,
            authority=f"https://login.microsoftonline.com/{settings.resolved_onenote_tenant_id}",
            token_cache=self.cache,
        )

    def get_access_token(self) -> str:
        scopes = self.settings.onenote_scope_list
        accounts = self.application.get_accounts()
        if accounts:
            result = self.application.acquire_token_silent(scopes, account=accounts[0])
            if result and "access_token" in result:
                self._persist_cache()
                return result["access_token"]

        flow = self.application.initiate_device_flow(scopes=scopes)
        if "user_code" not in flow:
            raise RuntimeError(f"Failed to start device code flow: {json.dumps(flow)}")
        print(flow["message"])
        result = self.application.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(f"Device code authentication failed: {result.get('error_description') or result}")
        self._persist_cache()
        return result["access_token"]

    def _persist_cache(self) -> None:
        if self.cache.has_state_changed:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(self.cache.serialize(), encoding="utf-8")
