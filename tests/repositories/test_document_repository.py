# EN: Tests for document repository persistence behavior.
# KO: DocumentRepository의 저장 및 조회 동작을 검증하는 테스트입니다.

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.repositories.document_repository import DocumentRepository
from app.schemas.artifact import DocumentType


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    await engine.dispose()


@pytest.mark.anyio
async def test_document_repository_creates_and_reads_document(session_factory) -> None:
    async with session_factory() as session:
        repository = DocumentRepository(session)

        created = await repository.create_document(
            document_id="DOC-001",
            project_id="PRJ-001",
            document_type=DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION,
            file_name="requirements.pdf",
            storage_path="s3://bucket/PRJ-001/raw/DOC-001/requirements.pdf",
        )

        found = await repository.get_document(
            project_id="PRJ-001",
            document_id="DOC-001",
        )

    assert created.document_id == "DOC-001"
    assert found is not None
    assert found.project_id == "PRJ-001"
    assert found.document_type == DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION


@pytest.mark.anyio
async def test_document_repository_scopes_document_lookup_by_project(
    session_factory,
) -> None:
    async with session_factory() as session:
        repository = DocumentRepository(session)
        await repository.create_document(
            document_id="DOC-001",
            project_id="PRJ-001",
            document_type=DocumentType.REQUIREMENT_SPEC,
            file_name="requirement-spec.pdf",
            storage_path="s3://bucket/PRJ-001/raw/DOC-001/requirement-spec.pdf",
        )

        found = await repository.get_document(
            project_id="PRJ-002",
            document_id="DOC-001",
        )

    assert found is None
