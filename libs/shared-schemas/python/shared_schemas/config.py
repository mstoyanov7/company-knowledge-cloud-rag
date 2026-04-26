from functools import lru_cache
import json

from pydantic import AliasChoices, Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "cloud-rag-diploma"
    app_env: str = "local"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    rag_api_host: str = "0.0.0.0"
    rag_api_port: int = 8080

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "cloudrag"
    postgres_user: str = "cloudrag"
    postgres_password: SecretStr = SecretStr("cloudrag")

    redis_host: str = "redis"
    redis_port: int = 6379

    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333

    sharepoint_graph_mode: str = "mock"
    graph_api_base_url: str = "https://graph.microsoft.com/v1.0"
    graph_token_scope: str = "https://graph.microsoft.com/.default"
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: SecretStr = SecretStr("")
    graph_sharepoint_hostname: str = "contoso.sharepoint.com"
    graph_sharepoint_site_scope: str = Field(
        default="sites/onboarding",
        validation_alias=AliasChoices("GRAPH_SHAREPOINT_SITE_SCOPE", "GRAPH_SHAREPOINT_SCOPE"),
    )
    graph_sharepoint_drive_scope: str = "Documents"
    onenote_graph_mode: str = "mock"
    onenote_auth_mode: str = "device_code"
    graph_onenote_tenant_id: str = ""
    graph_onenote_client_id: str = ""
    graph_onenote_scopes: str = "Notes.Read"
    graph_onenote_scope_mode: str = "site"
    graph_onenote_site_hostname: str = ""
    graph_onenote_site_scope: str = ""
    graph_onenote_notebook_scope: str = ""
    graph_onenote_scope: str = ""
    onenote_page_page_size: int = 100
    onenote_chunk_size_chars: int = 800
    onenote_chunk_overlap_chars: int = 120
    onenote_vector_collection: str = "onenote_chunks"
    onenote_token_cache_path: str = ".cache/onenote_token_cache.json"
    onenote_retry_attempts: int = 3
    onenote_retry_backoff_seconds: float = 1.0

    graph_notification_base_url: str = ""
    graph_notification_path: str = "/api/v1/graph/notifications"
    graph_lifecycle_notification_path: str = "/api/v1/graph/lifecycle"
    graph_subscription_client_state: SecretStr = SecretStr("cloudrag-graph-client-state")
    graph_sharepoint_subscription_resource: str = ""
    graph_sharepoint_subscription_change_type: str = "updated"
    graph_subscription_max_expiration_minutes: int = 4200
    graph_subscription_renewal_window_minutes: int = 720
    graph_subscription_renewal_interval_seconds: int = 3600

    ops_job_max_attempts: int = 5
    ops_job_base_backoff_seconds: int = 30
    ops_job_max_backoff_seconds: int = 1800
    ops_worker_batch_size: int = 10
    sharepoint_reconciliation_interval_seconds: int = 86400
    onenote_reconciliation_interval_seconds: int = 86400

    otel_enabled: bool = False
    otel_service_name: str = ""
    otel_exporter_otlp_endpoint: str = ""
    otel_console_exporter: bool = False

    sharepoint_sync_interval_seconds: int = 300
    onenote_sync_interval_seconds: int = 900
    worker_poll_interval_seconds: int = 30
    sharepoint_delta_page_size: int = 100
    sharepoint_chunk_size_chars: int = 800
    sharepoint_chunk_overlap_chars: int = 120
    sharepoint_vector_collection: str = "sharepoint_chunks"
    embedding_vector_size: int = 32

    default_llm_provider: str = "mock"
    default_embedding_provider: str = "mock"
    default_model_name: str = "mock-onboarding-assistant"
    mock_api_key: SecretStr = SecretStr("cloudrag-local-key")
    mock_top_k: int = 3
    rag_api_key: SecretStr = SecretStr("")
    retrieval_provider: str = "mock"
    retrieval_vector_collections: str = ""
    retrieval_candidate_multiplier: int = 3
    retrieval_score_threshold: float | None = None
    rerank_enabled: bool = True

    auth_enabled: bool = False
    auth_required: bool = False
    auth_tenant_id: str = ""
    auth_client_id: str = ""
    auth_allowed_audiences: str = ""
    auth_oidc_metadata_url: str = ""
    auth_required_scopes: str = ""
    auth_group_claim: str = "groups"
    auth_role_claim: str = "roles"
    auth_group_scope_map_json: str = "{}"
    auth_role_scope_map_json: str = "{}"
    auth_default_acl_tags: str = "public"
    auth_jwks_cache_seconds: int = 86400
    auth_leeway_seconds: int = 60
    security_audit_enabled: bool = True
    security_audit_log_to_db: bool = True

    openwebui_port: int = 3000

    @computed_field
    @property
    def postgres_dsn(self) -> str:
        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    @computed_field
    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    @computed_field
    @property
    def graph_notification_url(self) -> str:
        return _join_public_url(self.graph_notification_base_url, self.graph_notification_path)

    @computed_field
    @property
    def graph_lifecycle_notification_url(self) -> str:
        return _join_public_url(self.graph_notification_base_url, self.graph_lifecycle_notification_path)

    @computed_field
    @property
    def graph_sharepoint_scope(self) -> str:
        return self.graph_sharepoint_site_scope

    @computed_field
    @property
    def sharepoint_scope_key(self) -> str:
        site_scope = self.graph_sharepoint_site_scope.replace("/", "_")
        drive_scope = self.graph_sharepoint_drive_scope.replace("/", "_")
        return f"sharepoint::{self.graph_sharepoint_hostname}::{site_scope}::{drive_scope}"

    @computed_field
    @property
    def resolved_onenote_tenant_id(self) -> str:
        return self.graph_onenote_tenant_id or self.graph_tenant_id

    @computed_field
    @property
    def resolved_onenote_scope_mode(self) -> str:
        return (self.graph_onenote_scope_mode or "site").strip().lower()

    @computed_field
    @property
    def resolved_onenote_site_hostname(self) -> str:
        if self.resolved_onenote_scope_mode == "me":
            return "me"
        return self.graph_onenote_site_hostname or self.graph_sharepoint_hostname

    @computed_field
    @property
    def resolved_onenote_site_scope(self) -> str:
        if self.resolved_onenote_scope_mode == "me":
            return "onenote"
        return self.graph_onenote_site_scope or self.graph_sharepoint_site_scope

    @computed_field
    @property
    def onenote_scope_key(self) -> str:
        notebook_scope = (self.graph_onenote_notebook_scope or "all-notebooks").replace("/", "_").replace(" ", "_")
        if self.resolved_onenote_scope_mode == "me":
            return f"onenote::me::personal::{notebook_scope}"
        site_scope = self.resolved_onenote_site_scope.replace("/", "_")
        return f"onenote::{self.resolved_onenote_site_hostname}::{site_scope}::{notebook_scope}"

    @computed_field
    @property
    def onenote_scope_list(self) -> list[str]:
        return [scope for scope in self.graph_onenote_scopes.split() if scope]

    @computed_field
    @property
    def retrieval_collection_list(self) -> list[str]:
        if self.retrieval_vector_collections.strip():
            return [
                collection.strip()
                for collection in self.retrieval_vector_collections.split(",")
                if collection.strip()
            ]
        return list(dict.fromkeys([self.sharepoint_vector_collection, self.onenote_vector_collection]))

    @computed_field
    @property
    def resolved_auth_tenant_id(self) -> str:
        return self.auth_tenant_id or self.graph_tenant_id

    @computed_field
    @property
    def resolved_auth_client_id(self) -> str:
        return self.auth_client_id or self.graph_client_id

    @computed_field
    @property
    def auth_metadata_url(self) -> str:
        if self.auth_oidc_metadata_url:
            return self.auth_oidc_metadata_url
        if not self.resolved_auth_tenant_id:
            return ""
        return f"https://login.microsoftonline.com/{self.resolved_auth_tenant_id}/v2.0/.well-known/openid-configuration"

    @computed_field
    @property
    def auth_issuer(self) -> str:
        if not self.resolved_auth_tenant_id:
            return ""
        return f"https://login.microsoftonline.com/{self.resolved_auth_tenant_id}/v2.0"

    @computed_field
    @property
    def auth_audience_list(self) -> list[str]:
        configured = [audience.strip() for audience in self.auth_allowed_audiences.split(",") if audience.strip()]
        if configured:
            return configured
        if self.resolved_auth_client_id:
            return [self.resolved_auth_client_id, f"api://{self.resolved_auth_client_id}"]
        return []

    @computed_field
    @property
    def auth_required_scope_list(self) -> list[str]:
        return [scope.strip() for scope in self.auth_required_scopes.replace(",", " ").split() if scope.strip()]

    @computed_field
    @property
    def auth_default_acl_tag_list(self) -> list[str]:
        return [tag.strip() for tag in self.auth_default_acl_tags.split(",") if tag.strip()]

    @computed_field
    @property
    def auth_group_scope_map(self) -> dict[str, list[str]]:
        return _parse_scope_map(self.auth_group_scope_map_json)

    @computed_field
    @property
    def auth_role_scope_map(self) -> dict[str, list[str]]:
        return _parse_scope_map(self.auth_role_scope_map_json)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()


def _join_public_url(base_url: str, path: str) -> str:
    if not base_url:
        return ""
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _parse_scope_map(value: str) -> dict[str, list[str]]:
    if not value.strip():
        return {}
    raw = json.loads(value)
    parsed: dict[str, list[str]] = {}
    for claim_value, acl_tags in raw.items():
        if isinstance(acl_tags, str):
            parsed[str(claim_value)] = [tag.strip() for tag in acl_tags.split(",") if tag.strip()]
            continue
        parsed[str(claim_value)] = [str(tag).strip() for tag in acl_tags if str(tag).strip()]
    return parsed
