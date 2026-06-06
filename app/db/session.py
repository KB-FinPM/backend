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


async def dispose_db() -> None:
    await engine.dispose()
