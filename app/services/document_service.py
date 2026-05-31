# EN: Business service for project-scoped document operations.
# KO: 프로젝트 범위 문서 작업을 담당하는 비즈니스 서비스입니다.

from app.repositories.document_repository import DocumentRepository
from app.schemas.artifact import DocumentMetadata, DocumentStatus, DocumentType


class DocumentService:
    """Coordinates document use cases without exposing repositories to routers."""

    def __init__(self, document_repository: DocumentRepository) -> None:
        self.document_repository = document_repository

    async def create_document(
        self,
        *,
        document_id: str,
        project_id: str,
        document_type: DocumentType,
        file_name: str,
        storage_path: str,
        status: DocumentStatus = DocumentStatus.UPLOADED,
    ) -> DocumentMetadata:
        return await self.document_repository.create_document(
            document_id=document_id,
            project_id=project_id,
            document_type=document_type,
            file_name=file_name,
            storage_path=storage_path,
            status=status,
        )

    async def get_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> DocumentMetadata | None:
        return await self.document_repository.get_document(
            project_id=project_id,
            document_id=document_id,
        )

    async def list_documents(self, *, project_id: str) -> list[DocumentMetadata]:
        return await self.document_repository.list_documents_by_project(
            project_id=project_id,
        )
