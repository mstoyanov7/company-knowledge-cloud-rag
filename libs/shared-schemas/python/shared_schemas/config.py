from functools import lru_cache

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

    redis_host: str = "redis"
    redis_port: int = 6379

    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333

    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: SecretStr = SecretStr("")
    graph_sharepoint_scope: str = ""
    graph_onenote_scope: str = ""

    sharepoint_sync_interval_seconds: int = 300
    onenote_sync_interval_seconds: int = 900
    worker_poll_interval_seconds: int = 30

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


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()
