# EN: FastAPI dependency factories for repositories and shared resources.
# KO: Repository 및 공통 리소스를 제공하는 FastAPI 의존성 팩토리입니다.

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.db.session import get_session
from app.repositories.artifact_repository import ArtifactRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.template_repository import TemplateRepository
from app.orchestrator.generation_orchestrator import generation_orchestrator
from app.rag.retrieval import RetrievalService
from app.services.artifact_service import ArtifactService
from app.services.document_service import DocumentService
from app.services.generation_service import GenerationService
from app.services.template_service import TemplateService


def get_document_repository(
    session: AsyncSession = Depends(get_session),
) -> DocumentRepository:
    return DocumentRepository(session)


def get_artifact_repository(
    session: AsyncSession = Depends(get_session),
) -> ArtifactRepository:
    return ArtifactRepository(session)


def get_template_repository(
    session: AsyncSession = Depends(get_session),
) -> TemplateRepository:
    return TemplateRepository(session)


def get_document_service(
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> DocumentService:
    return DocumentService(document_repository)


def get_artifact_service(
    artifact_repository: ArtifactRepository = Depends(get_artifact_repository),
) -> ArtifactService:
    return ArtifactService(artifact_repository)


def get_generation_service() -> GenerationService:
    return GenerationService(generation_orchestrator)


def get_retrieval_service(
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> RetrievalService:
    return RetrievalService(document_repository)


def get_template_service(
    template_repository: TemplateRepository = Depends(get_template_repository),
) -> TemplateService:
    return TemplateService(template_repository)
