from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "development"
    DEBUG: bool = True
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:5176",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "http://127.0.0.1:5176",
        "https://d2xtqtnbdz7asr.cloudfront.net",
    ]

    AWS_REGION: str = "ap-northeast-2"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_CA_BUNDLE: str = ""
    AWS_VERIFY_SSL: bool = True

    S3_BUCKET_NAME: str = "kbds-s3-finpm"
    S3_STORAGE_BACKEND: str = "mock"
    S3_UPLOAD_PREFIX: str = "storage/upload_files"
    S3_TEMPLATE_PREFIX: str = "storage/template_files"
    S3_GENERATED_PREFIX: str = "storage/generated_files"

    BEDROCK_MODEL_ID: str = "apac.anthropic.claude-sonnet-4-20250514-v1:0"
    BEDROCK_INFERENCE_PROFILE_ID: str = "apac.anthropic.claude-sonnet-4-20250514-v1:0"
    DATABASE_URL: str = "sqlite+aiosqlite:///./finpm.db"

    VECTOR_STORE_TYPE: str = "pgvector"

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug_flag(cls, value: Any) -> Any:
        if isinstance(value, str) and value.lower() in {
            "release",
            "prod",
            "production",
        }:
            return False

        return value


def normalize_async_database_url(database_url: str) -> str:
    """Return a SQLAlchemy async-driver URL for AsyncEngine.

    SQLAlchemy AsyncEngine cannot use sync PostgreSQL drivers such as
    psycopg2. This helper keeps sqlite async URLs unchanged and rewrites
    common PostgreSQL sync URLs to asyncpg.
    """
    if not database_url:
        return database_url

    replacements = {
        "postgresql+psycopg2://": "postgresql+asyncpg://",
        "postgresql+psycopg://": "postgresql+asyncpg://",
        "postgresql://": "postgresql+asyncpg://",
        "postgres://": "postgresql+asyncpg://",
    }
    for prefix, replacement in replacements.items():
        if database_url.startswith(prefix):
            return replacement + database_url[len(prefix):]

    return database_url


settings = Settings()
