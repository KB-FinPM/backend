from pathlib import Path

from app.core.config import ENV_FILE, Settings


def test_settings_env_file_points_to_backend_env() -> None:
    assert ENV_FILE == Path(__file__).resolve().parents[2] / ".env"


def test_settings_defaults_match_env_example_baseline() -> None:
    settings = Settings(_env_file=None)

    assert settings.APP_ENV == "development"
    assert settings.AWS_REGION == "ap-northeast-2"
    assert settings.AWS_VERIFY_SSL is True
    assert settings.DATABASE_URL == "sqlite+aiosqlite:///./finpm.db"
    assert settings.S3_STORAGE_BACKEND == "mock"


def test_settings_can_load_explicit_env_file(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=test",
                "DEBUG=release",
                "DATABASE_URL=sqlite+aiosqlite:///./test.db",
                "ALLOWED_ORIGINS=[\"http://localhost:9999\"]",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.APP_ENV == "test"
    assert settings.DEBUG is False
    assert settings.DATABASE_URL == "sqlite+aiosqlite:///./test.db"
    assert settings.ALLOWED_ORIGINS == ["http://localhost:9999"]
