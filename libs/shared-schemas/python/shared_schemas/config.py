from functools import lru_cache

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
    graph_onenote_scopes: str = "Notes.Read.All offline_access openid profile"
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
    def resolved_onenote_site_hostname(self) -> str:
        return self.graph_onenote_site_hostname or self.graph_sharepoint_hostname

    @computed_field
    @property
    def resolved_onenote_site_scope(self) -> str:
        return self.graph_onenote_site_scope or self.graph_sharepoint_site_scope

    @computed_field
    @property
    def onenote_scope_key(self) -> str:
        site_scope = self.resolved_onenote_site_scope.replace("/", "_")
        notebook_scope = (self.graph_onenote_notebook_scope or "all-notebooks").replace("/", "_").replace(" ", "_")
        return f"onenote::{self.resolved_onenote_site_hostname}::{site_scope}::{notebook_scope}"

    @computed_field
    @property
    def onenote_scope_list(self) -> list[str]:
        return [scope for scope in self.graph_onenote_scopes.split() if scope]


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()
