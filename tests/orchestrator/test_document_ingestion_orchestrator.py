# EN: Tests for uploaded document ingestion orchestration.
# KO: 업로드 문서 수집/처리 Orchestrator 테스트입니다.

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.orchestrator.document_ingestion_orchestrator import (
    DocumentIngestionOrchestrator,
)
from app.repositories.document_repository import DocumentRepository
from app.schemas.artifact import DocumentStatus, DocumentType


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
async def test_document_ingestion_orchestrator_indexes_supported_text(
    session_factory,
) -> None:
    async with session_factory() as session:
        repository = DocumentRepository(session)
        orchestrator = DocumentIngestionOrchestrator()

        document = await orchestrator.ingest_uploaded_document(
            document_repository=repository,
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
    assert chunks[0].chunk_metadata["parser_name"] == "DocumentParserAgent"


@pytest.mark.anyio
async def test_document_ingestion_orchestrator_keeps_unsupported_file_uploaded(
    session_factory,
) -> None:
    async with session_factory() as session:
        repository = DocumentRepository(session)
        orchestrator = DocumentIngestionOrchestrator()

        document = await orchestrator.ingest_uploaded_document(
            document_repository=repository,
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


@pytest.mark.anyio
async def test_document_ingestion_orchestrator_uses_preparsed_context(
    session_factory,
) -> None:
    async with session_factory() as session:
        repository = DocumentRepository(session)
        orchestrator = DocumentIngestionOrchestrator()

        document = await orchestrator.ingest_uploaded_document(
            document_repository=repository,
            document_id="DOC-001",
            project_id="PRJ-001",
            document_type=DocumentType.REQUIREMENT_SPEC,
            file_name="requirements.pdf",
            storage_path="s3://bucket/requirements.pdf",
            file_bytes=b"%PDF",
            parsed_context={
                "text": "The system shall support login.",
                "metadata": {"content_type": "application/pdf"},
                "parser_name": "InputOrchestrator",
            },
        )
        chunks = await repository.list_chunks_by_document(
            project_id="PRJ-001",
            document_id="DOC-001",
        )

    assert document.status == DocumentStatus.INDEXED
    assert len(chunks) == 1
    assert chunks[0].chunk_metadata["parser_name"] == "InputOrchestrator"
    assert chunks[0].chunk_metadata["content_type"] == "application/pdf"
