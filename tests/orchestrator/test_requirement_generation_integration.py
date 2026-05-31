# EN: Integration-style test for requirement generation over stored chunks.
# KO: 저장된 chunk 기반 요구사항 생성 통합형 테스트입니다.

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.agents.core_agents.requirement_agent.agent import RequirementAgent
from app.agents.core_agents.validator_agent.agent import ValidatorAgent
from app.db.base import Base
from app.orchestrator.generation_orchestrator import GenerationOrchestrator
from app.rag.retrieval import RetrievalService
from app.repositories.artifact_repository import ArtifactRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.artifact import ArtifactType, DocumentType
from app.schemas.request import GenerationRequest
from app.services.artifact_service import ArtifactService


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
async def test_requirement_generation_uses_stored_chunks_and_persists_artifact(
    session_factory,
) -> None:
    async with session_factory() as session:
        document_repository = DocumentRepository(session)
        artifact_repository = ArtifactRepository(session)
        await document_repository.create_document(
            document_id="DOC-001",
            project_id="PRJ-001",
            document_type=DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION,
            file_name="requirements.txt",
            storage_path="s3://bucket/requirements.txt",
        )
        await document_repository.create_chunk(
            chunk_id="CHUNK-001",
            project_id="PRJ-001",
            document_id="DOC-001",
            chunk_index=0,
            text="Login is required. Users must authenticate before viewing data.",
        )

        orchestrator = GenerationOrchestrator(
            retrieval=RetrievalService(document_repository),
            requirement_generator=RequirementAgent(),
            validator=ValidatorAgent(),
        )
        artifact_service = ArtifactService(artifact_repository)
        request = GenerationRequest(
            project_id="PRJ-001",
            source_document_ids=["DOC-001"],
            source_document_type=DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION,
            target_artifact_type=ArtifactType.REQUIREMENT_SPEC,
            query="Login",
            permission_scope=["project:read", "artifact:generate"],
        )

        response = await orchestrator.generate_requirement(
            request,
            artifact_service=artifact_service,
        )

    assert response.success is True
    assert response.result["artifact"]["artifact_id"].startswith("ART-")
    assert response.result["generated"]["artifact_type"] == "REQUIREMENT_SPEC"
    assert response.result["generated"]["requirements"][0]["source_chunk_ids"] == [
        "CHUNK-001"
    ]
