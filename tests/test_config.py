from pathlib import Path

from shared_schemas import AppSettings


def test_settings_load_from_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / "test.env"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=test",
                "RAG_API_PORT=9090",
                "POSTGRES_PASSWORD=supersecret",
                "GRAPH_SHAREPOINT_SITE_SCOPE=sites/engineering-onboarding",
                "GRAPH_SHAREPOINT_DRIVE_SCOPE=Employee Documents",
                "MOCK_API_KEY=test-key",
            ]
        ),
        encoding="utf-8",
    )

    settings = AppSettings(_env_file=env_file)

    assert settings.app_env == "test"
    assert settings.rag_api_port == 9090
    assert settings.graph_sharepoint_scope == "sites/engineering-onboarding"
    assert settings.graph_sharepoint_drive_scope == "Employee Documents"
    assert settings.mock_api_key.get_secret_value() == "test-key"
    assert settings.postgres_dsn == "postgresql://cloudrag:supersecret@postgres:5432/cloudrag"
