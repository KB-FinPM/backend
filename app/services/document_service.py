# EN: Business service for project-scoped document operations.
# KO: 프로젝트 범위 문서 작업을 담당하는 비즈니스 서비스입니다.

from pathlib import PurePath

from app.orchestrator.document_ingestion_orchestrator import (
    DocumentIngestionOrchestrator,
    document_ingestion_orchestrator,
)
from app.repositories.document_repository import DocumentRepository
from app.schemas.artifact import DocumentMetadata, DocumentStatus, DocumentType
from app.storage.s3 import S3Service


class DocumentService:
    """Coordinates document use cases without exposing repositories to routers."""

    def __init__(
        self,
        document_repository: DocumentRepository,
        storage_service: S3Service,
        ingestion_orchestrator: DocumentIngestionOrchestrator = (
            document_ingestion_orchestrator
        ),
    ) -> None:
        self.document_repository = document_repository
        self.storage_service = storage_service
        self.ingestion_orchestrator = ingestion_orchestrator

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

    async def upload_to_storage(
        self,
        *,
        file_bytes: bytes,
        project_id: str,
        document_id: str,
        file_name: str,
        upload_prefix: str,
    ) -> str:
        """Upload file to S3 and return storage path. Abstraction layer for router."""
        safe_file_name = PurePath(file_name).name
        storage_key = f"{upload_prefix}/{project_id}/raw/{document_id}/{safe_file_name}"
        storage_path = await self.storage_service.upload(
            file_bytes=file_bytes,
            key=storage_key,
        )
        return storage_path

    async def ingest_uploaded_document(
        self,
        *,
        document_id: str,
        project_id: str,
        document_type: DocumentType,
        file_name: str,
        storage_path: str,
        file_bytes: bytes,
        parsed_context: dict | None = None,
    ) -> DocumentMetadata:
        return await self.ingestion_orchestrator.ingest_uploaded_document(
            document_repository=self.document_repository,
            document_id=document_id,
            project_id=project_id,
            document_type=document_type,
            file_name=file_name,
            storage_path=storage_path,
            file_bytes=file_bytes,
            parsed_context=parsed_context,
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

    async def delete_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> bool:
        return await self.document_repository.delete_document(
            project_id=project_id,
            document_id=document_id,
        )
