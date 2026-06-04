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
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

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

    BEDROCK_MODEL_ID: str = "anthropic.claude-sonnet-4-5"

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


settings = Settings()
