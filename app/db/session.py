# EN: Async SQLAlchemy engine, session factory, and FastAPI DB dependency.
# KO: async SQLAlchemy 엔진, 세션 팩토리, FastAPI DB 의존성입니다.

import ssl
from collections.abc import AsyncGenerator

import certifi
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import normalize_async_database_url, settings
from app.db.base import Base

database_url = normalize_async_database_url(settings.DATABASE_URL)
connect_args: dict[str, object] = {}
if database_url.startswith("postgresql"):
    if settings.DATABASE_SSL_VERIFY:
        ssl_context = ssl.create_default_context(
            cafile=settings.AWS_CA_BUNDLE or certifi.where()
        )
    else:
        ssl_context = ssl._create_unverified_context()
    connect_args["ssl"] = ssl_context

engine = create_async_engine(
    database_url,
    echo=settings.SQLALCHEMY_ECHO,
    pool_pre_ping=True,
    connect_args=connect_args,
    hide_parameters=settings.SQLALCHEMY_HIDE_PARAMETERS,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.run_sync(Base.metadata.create_all)
        await _ensure_project_columns(connection)
        await _ensure_action_item_columns(connection)


async def dispose_db() -> None:
    await engine.dispose()


async def _ensure_action_item_columns(connection) -> None:
    columns = {
        "description": "TEXT",
        "due_date_text": "VARCHAR(100)",
        "related_document": "VARCHAR(200)",
        "source_type": "VARCHAR(40) DEFAULT 'MEETING_MINUTES'",
        "updated_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        "completed_at": "DATETIME",
    }
    if connection.dialect.name == "sqlite":
        result = await connection.execute(text("PRAGMA table_info(action_items)"))
        existing_columns = {row[1] for row in result.fetchall()}
        for column_name, column_sql in columns.items():
            if column_name not in existing_columns:
                await connection.execute(
                    text(f"ALTER TABLE action_items ADD COLUMN {column_name} {column_sql}")
                )
        return

    if connection.dialect.name == "postgresql":
        postgres_columns = {
            **columns,
            "updated_at": "TIMESTAMP WITH TIME ZONE DEFAULT now()",
            "completed_at": "TIMESTAMP WITH TIME ZONE",
        }
        for column_name, column_sql in postgres_columns.items():
            await connection.execute(
                text(
                    f"ALTER TABLE action_items ADD COLUMN IF NOT EXISTS "
                    f"{column_name} {column_sql}"
                )
            )


async def _ensure_project_columns(connection) -> None:
    columns = {
        "start_date": "DATE",
        "end_date": "DATE",
    }
    if connection.dialect.name == "sqlite":
        result = await connection.execute(text("PRAGMA table_info(projects)"))
        existing_columns = {row[1] for row in result.fetchall()}
        for column_name, column_sql in columns.items():
            if column_name not in existing_columns:
                await connection.execute(
                    text(f"ALTER TABLE projects ADD COLUMN {column_name} {column_sql}")
                )
        return

    if connection.dialect.name == "postgresql":
        for column_name, column_sql in columns.items():
            await connection.execute(
                text(
                    f"ALTER TABLE projects ADD COLUMN IF NOT EXISTS "
                    f"{column_name} {column_sql}"
                )
            )
