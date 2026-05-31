# EN: Repository for document metadata and document chunk persistence.
# KO: 문서 메타데이터와 문서 Chunk 저장을 담당하는 Repository입니다.

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentChunkModel, DocumentModel
from app.schemas.artifact import DocumentMetadata, DocumentStatus, DocumentType


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
        document = DocumentModel(
            document_id=document_id,
            project_id=project_id,
            document_type=document_type.value,
            file_name=file_name,
            storage_path=storage_path,
            status=status.value,
        )
        self.session.add(document)
        await self.session.commit()
        await self.session.refresh(document)
        return self._to_metadata(document)

    async def get_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Optional[DocumentMetadata]:
        statement = select(DocumentModel).where(
            DocumentModel.project_id == project_id,
            DocumentModel.document_id == document_id,
        )
        result = await self.session.execute(statement)
        document = result.scalar_one_or_none()
        if document is None:
            return None
        return self._to_metadata(document)

    async def list_documents_by_project(
        self,
        *,
        project_id: str,
    ) -> list[DocumentMetadata]:
        statement = (
            select(DocumentModel)
            .where(DocumentModel.project_id == project_id)
            .order_by(DocumentModel.created_at.desc())
        )
        result = await self.session.execute(statement)
        return [self._to_metadata(document) for document in result.scalars().all()]

    async def update_document_status(
        self,
        *,
        project_id: str,
        document_id: str,
        status: DocumentStatus,
    ) -> Optional[DocumentMetadata]:
        statement = select(DocumentModel).where(
            DocumentModel.project_id == project_id,
            DocumentModel.document_id == document_id,
        )
        result = await self.session.execute(statement)
        document = result.scalar_one_or_none()
        if document is None:
            return None

        document.status = status.value
        await self.session.commit()
        await self.session.refresh(document)

        return self._to_metadata(document)

    async def create_chunk(
        self,
        *,
        chunk_id: str,
        project_id: str,
        document_id: str,
        chunk_index: int,
        text: str,
        section_title: Optional[str] = None,
        chunk_metadata: Optional[dict[str, Any]] = None,
        embedding: Optional[list[float]] = None,
    ) -> DocumentChunkModel:
        chunk = DocumentChunkModel(
            chunk_id=chunk_id,
            project_id=project_id,
            document_id=document_id,
            chunk_index=chunk_index,
            text=text,
            section_title=section_title,
            chunk_metadata=chunk_metadata or {},
            embedding=embedding,
        )
        self.session.add(chunk)
        await self.session.commit()
        await self.session.refresh(chunk)
        return chunk

    async def list_chunks_by_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> list[DocumentChunkModel]:
        statement = (
            select(DocumentChunkModel)
            .where(
                DocumentChunkModel.project_id == project_id,
                DocumentChunkModel.document_id == document_id,
            )
            .order_by(DocumentChunkModel.chunk_index.asc())
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    def _to_metadata(self, document: DocumentModel) -> DocumentMetadata:
        return DocumentMetadata(
            document_id=document.document_id,
            project_id=document.project_id,
            document_type=DocumentType(document.document_type),
            file_name=document.file_name,
            storage_path=document.storage_path,
            status=DocumentStatus(document.status),
        )
