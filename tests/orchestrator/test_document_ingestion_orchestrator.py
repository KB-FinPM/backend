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


class FakeEmbeddingService:
    async def embed_texts(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


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
async def test_document_ingestion_orchestrator_marks_unsupported_file_failed(
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
            file_name="requirements.exe",
            storage_path="s3://bucket/requirements.exe",
            file_bytes=b"binary",
        )
        chunks = await repository.list_chunks_by_document(
            project_id="PRJ-001",
            document_id="DOC-001",
        )

    assert document.status == DocumentStatus.FAILED
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


@pytest.mark.anyio
async def test_document_ingestion_orchestrator_indexes_wbs_rows_once(session_factory) -> None:
    async with session_factory() as session:
        repository = DocumentRepository(session)
        orchestrator = DocumentIngestionOrchestrator(
            embedding_service=FakeEmbeddingService()
        )

        document = await orchestrator.ingest_uploaded_document(
            document_repository=repository,
            document_id="DOC-001",
            project_id="PRJ-001",
            document_type=DocumentType.WBS,
            file_name="wbs.xlsx",
            storage_path="s3://bucket/wbs.xlsx",
            file_bytes=b"binary",
            parsed_context={
                "text": "# WBS",
                "metadata": {"artifact_type": "WBS"},
                "wbs_context": {
                    "rows": [
                        {"row_number": 1, "title": "요구사항정의", "wbs_id": "0"},
                        {"row_number": 2, "title": "분석", "wbs_id": "1"},
                    ]
                },
            },
        )
        chunks = await repository.list_chunks_by_document(
            project_id="PRJ-001",
            document_id="DOC-001",
        )

    assert document.status == DocumentStatus.INDEXED
    assert len(chunks) == 2
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert [chunk.section_title for chunk in chunks] == ["요구사항정의", "분석"]
