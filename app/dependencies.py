# EN: FastAPI dependency factories for repositories and shared resources.
# KO: Repository 및 공통 리소스를 제공하는 FastAPI 의존성 팩토리입니다.

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.db.session import get_session
from app.repositories.artifact_repository import ArtifactRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.template_repository import TemplateRepository


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
