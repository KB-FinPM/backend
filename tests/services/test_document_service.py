# EN: Tests for document service ingestion behavior.
# KO: 문서 서비스 수집 동작 테스트입니다.

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.repositories.document_repository import DocumentRepository
from app.schemas.artifact import DocumentStatus, DocumentType
from app.services.document_service import DocumentService


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
async def test_document_service_ingests_supported_text_file(session_factory) -> None:
    async with session_factory() as session:
        repository = DocumentRepository(session)
        service = DocumentService(repository)

        document = await service.ingest_uploaded_document(
            document_id="DOC-001",
            project_id="PRJ-001",
            document_type=DocumentType.REQUIREMENT_SPEC,
            file_name="requirements.txt",
            storage_path="s3://bucket/requirements.txt",
            file_bytes=b"TITLE:\nThe system shall support login.",
        )
        chunks = await repository.list_chunks_by_document(
            project_id="PRJ-001",
            document_id="DOC-001",
        )

    assert document.status == DocumentStatus.INDEXED
    assert len(chunks) == 1
    assert chunks[0].text == "TITLE:\nThe system shall support login."
    assert chunks[0].chunk_metadata["parser_name"] == "DocumentParserAgent"


@pytest.mark.anyio
async def test_document_service_keeps_unsupported_file_uploaded(session_factory) -> None:
    async with session_factory() as session:
        repository = DocumentRepository(session)
        service = DocumentService(repository)

        document = await service.ingest_uploaded_document(
            document_id="DOC-001",
            project_id="PRJ-001",
            document_type=DocumentType.REQUIREMENT_SPEC,
            file_name="requirements.pdf",
            storage_path="s3://bucket/requirements.pdf",
            file_bytes=b"%PDF",
        )
        chunks = await repository.list_chunks_by_document(
            project_id="PRJ-001",
            document_id="DOC-001",
        )

    assert document.status == DocumentStatus.UPLOADED
    assert chunks == []
