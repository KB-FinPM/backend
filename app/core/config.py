from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # 앱
    APP_ENV: str = "development"
    DEBUG: bool = True
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # AWS
    AWS_REGION: str = "ap-northeast-2"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""

    # S3
    S3_BUCKET_NAME: str = ""

    # Bedrock
    BEDROCK_MODEL_ID: str = "anthropic.claude-sonnet-4-5"

    # DB (Aurora PostgreSQL)
    DATABASE_URL: str = "sqlite+aiosqlite:///./finpm.db"  # 로컬 개발용 SQLite

    # Vector Store
    VECTOR_STORE_TYPE: str = "chroma"  # chroma | pgvector | opensearch

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
