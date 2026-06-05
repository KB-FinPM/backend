# EN: Tests for retrieval service project and permission scoping.
# KO: Retrieval 서비스의 프로젝트/권한 범위 테스트입니다.

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.rag.retrieval import RetrievalService
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
async def test_retrieval_service_returns_project_scoped_chunks(session_factory) -> None:
    async with session_factory() as session:
        repository = DocumentRepository(session)
        await repository.create_document(
            document_id="DOC-001",
            project_id="PRJ-001",
            document_type=DocumentType.REQUIREMENT_SPEC,
            file_name="requirements.txt",
            storage_path="s3://bucket/requirements.txt",
        )
        await repository.create_chunk(
            chunk_id="CHUNK-001",
            project_id="PRJ-001",
            document_id="DOC-001",
            chunk_index=0,
            text="Login requirement",
            chunk_metadata={"source_file_name": "requirements.txt"},
        )
        service = RetrievalService(repository)

        results = await service.search(
            project_id="PRJ-001",
            permission_scope=["project:read"],
            query="login",
        )

    assert results == [
        {
            "chunk_id": "CHUNK-001",
            "project_id": "PRJ-001",
            "document_id": "DOC-001",
            "chunk_index": 0,
            "text": "Login requirement",
            "section_title": None,
            "metadata": {"source_file_name": "requirements.txt"},
        }
    ]


@pytest.mark.anyio
async def test_retrieval_service_requires_project_read_scope(session_factory) -> None:
    async with session_factory() as session:
        repository = DocumentRepository(session)
        service = RetrievalService(repository)

        results = await service.search(
            project_id="PRJ-001",
            permission_scope=["artifact:generate"],
            query="login",
        )

    assert results == []


@pytest.mark.anyio
async def test_retrieval_service_filters_by_source_document_ids(
    session_factory,
) -> None:
    async with session_factory() as session:
        repository = DocumentRepository(session)
        await repository.create_document(
            document_id="DOC-001",
            project_id="PRJ-001",
            document_type=DocumentType.REQUIREMENT_SPEC,
            file_name="selected.txt",
            storage_path="s3://bucket/selected.txt",
        )
        await repository.create_document(
            document_id="DOC-002",
            project_id="PRJ-001",
            document_type=DocumentType.REQUIREMENT_SPEC,
            file_name="other.txt",
            storage_path="s3://bucket/other.txt",
        )
        await repository.create_chunk(
            chunk_id="CHUNK-001",
            project_id="PRJ-001",
            document_id="DOC-001",
            chunk_index=0,
            text="Selected document login requirement",
        )
        await repository.create_chunk(
            chunk_id="CHUNK-002",
            project_id="PRJ-001",
            document_id="DOC-002",
            chunk_index=0,
            text="Other document login requirement",
        )
        service = RetrievalService(repository)

        results = await service.search(
            project_id="PRJ-001",
            permission_scope=["project:read"],
            query="login",
            document_ids=["DOC-001"],
        )

    assert [result["document_id"] for result in results] == ["DOC-001"]


@pytest.mark.anyio
async def test_retrieval_service_falls_back_to_selected_document_chunks(
    session_factory,
) -> None:
    async with session_factory() as session:
        repository = DocumentRepository(session)
        await repository.create_document(
            document_id="DOC-001",
            project_id="PRJ-001",
            document_type=DocumentType.REQUIREMENT_SPEC,
            file_name="selected.txt",
            storage_path="s3://bucket/selected.txt",
        )
        await repository.create_chunk(
            chunk_id="CHUNK-001",
            project_id="PRJ-001",
            document_id="DOC-001",
            chunk_index=0,
            text="Login requirement",
        )
        service = RetrievalService(repository)

        results = await service.search(
            project_id="PRJ-001",
            permission_scope=["project:read"],
            query="Create a WBS from this document",
            document_ids=["DOC-001"],
        )

    assert [result["chunk_id"] for result in results] == ["CHUNK-001"]
