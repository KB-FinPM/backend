# EN: Async SQLAlchemy engine, session factory, and FastAPI DB dependency.
# KO: async SQLAlchemy 엔진, 세션 팩토리, FastAPI DB 의존성입니다.

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import normalize_async_database_url, settings
from app.db.base import Base

engine = create_async_engine(
    normalize_async_database_url(settings.DATABASE_URL),
    echo=settings.DEBUG,
    pool_pre_ping=True,
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
        }
        for column_name, column_sql in postgres_columns.items():
            await connection.execute(
                text(
                    f"ALTER TABLE action_items ADD COLUMN IF NOT EXISTS "
                    f"{column_name} {column_sql}"
                )
            )
