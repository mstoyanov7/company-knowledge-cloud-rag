from functools import lru_cache
import json

from pydantic import SecretStr, computed_field
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

    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333

    graph_api_base_url: str = "https://graph.microsoft.com/v1.0"
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    onenote_graph_mode: str = "mock"
    onenote_auth_mode: str = "device_code"
    graph_onenote_tenant_id: str = ""
    graph_onenote_client_id: str = ""
    graph_onenote_scopes: str = "Notes.Read"
    graph_onenote_scope_mode: str = "site"
    graph_onenote_site_hostname: str = ""
    graph_onenote_site_scope: str = ""
    graph_onenote_notebook_scope: str = ""
    onenote_page_page_size: int = 100
    onenote_chunk_size_chars: int = 2000
    onenote_chunk_overlap_chars: int = 300
    onenote_procedure_chunk_max_chars: int = 5000
    rag_context_max_chars: int = 10000
    onenote_vector_collection: str = "onenote_chunks"
    onenote_token_cache_path: str = ".cache/onenote_token_cache.json"
    onenote_retry_attempts: int = 6
    onenote_retry_backoff_seconds: float = 2.0
    onenote_request_delay_seconds: float = 0.0
    onenote_incremental_lookback_seconds: int = 300
    attachment_storage_dir: str = ".cache/attachments"

    ops_job_max_attempts: int = 5
    ops_job_base_backoff_seconds: int = 30
    ops_job_max_backoff_seconds: int = 1800
    ops_worker_batch_size: int = 10
    onenote_reconciliation_interval_seconds: int = 86400

    otel_enabled: bool = False
    otel_service_name: str = ""
    otel_exporter_otlp_endpoint: str = ""
    otel_console_exporter: bool = False

    onenote_sync_interval_seconds: int = 900
    # Automatic OneNote sync runs once per day at this local clock time (HH:MM)
    # in onenote_sync_timezone, instead of polling on a fixed seconds interval.
    onenote_sync_daily_time: str = "02:00"
    onenote_sync_timezone: str = "Europe/Sofia"
    worker_poll_interval_seconds: int = 30
    embedding_vector_size: int = 768

    default_llm_provider: str = "mock"
    default_embedding_provider: str = "ollama"
    embedding_model_name: str = "nomic-embed-text"

    embedding_base_url: str = ""
    embedding_api_key: SecretStr = SecretStr("")

    # Redis-backed query-embedding cache (rag-api). An empty redis_host disables
    # it; the cache also degrades to a no-op if Redis is unreachable, so the API
    # answers correctly with or without Redis present.
    redis_host: str = ""
    redis_port: int = 6379
    query_embedding_cache_enabled: bool = True
    query_embedding_cache_ttl_seconds: int = 3600
    default_model_name: str = "mock-onboarding-assistant"
    llm_openai_base_url: str = "http://host.docker.internal:11434/v1"
    llm_openai_api_key: SecretStr = SecretStr("ollama")
    llm_request_timeout_seconds: float = 120.0
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1400
    mock_api_key: SecretStr = SecretStr("cloudrag-local-key")
    mock_top_k: int = 3

    mock_corpus_path: str = ""
    rag_api_key: SecretStr = SecretStr("")
    topics_config_path: str = "config/topics.json"
    retrieval_provider: str = "mock"
    retrieval_vector_collections: str = ""
    retrieval_candidate_multiplier: int = 3
    retrieval_score_threshold: float | None = None
    retrieval_min_keyword_overlap: int = 1

    retrieval_lexical_scan_limit: int = 0

    clarify_enabled: bool = True
    clarify_closeness_ratio: float = 0.6
    clarify_max_options: int = 5

    answer_guard_repair_enabled: bool = True
    rerank_enabled: bool = True

    semantic_fixture_path: str = "eval/datasets/semantic_fixture.json"

    retrieval_min_semantic_score: float = 0.0

    mock_lexical_scoring: str = "overlap"
    rag_debug_enabled: bool = False
    app_database_url: str = "sqlite:///./.cache/rag_api.sqlite3"

    auth_enabled: bool = False
    auth_required: bool = False
    auth_session_secret: SecretStr = SecretStr("local-dev-session-secret-change-me")
    auth_session_ttl_hours: int = 168
    auth_registration_tenant_id: str = ""
    auth_registration_acl_tags: str = ""
    auth_bootstrap_admin_email: str = ""
    auth_bootstrap_admin_password: SecretStr = SecretStr("")
    auth_bootstrap_admin_name: str = ""
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
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    @computed_field
    @property
    def resolved_embedding_base_url(self) -> str:
        return self.embedding_base_url or self.llm_openai_base_url

    @computed_field
    @property
    def resolved_embedding_api_key(self) -> str:
        configured = self.embedding_api_key.get_secret_value()
        return configured or self.llm_openai_api_key.get_secret_value()

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
        return self.graph_onenote_site_hostname

    @computed_field
    @property
    def resolved_onenote_site_scope(self) -> str:
        if self.resolved_onenote_scope_mode == "me":
            return "onenote"
        return self.graph_onenote_site_scope

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
        return [self.onenote_vector_collection]

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
    def auth_registration_acl_tag_list(self) -> list[str]:
        configured = [tag.strip() for tag in self.auth_registration_acl_tags.split(",") if tag.strip()]
        return configured or self.auth_default_acl_tag_list

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
