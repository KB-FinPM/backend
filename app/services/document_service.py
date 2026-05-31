# EN: Business service for project-scoped document operations.
# KO: 프로젝트 범위 문서 작업을 담당하는 비즈니스 서비스입니다.

from uuid import uuid4

from app.agents.input_agents.document_parser_agent.agent import (
    DocumentParserAgent,
    document_parser_agent,
)
from app.rag.chunking import split_text_into_chunks
from app.repositories.document_repository import DocumentRepository
from app.schemas.artifact import DocumentMetadata, DocumentStatus, DocumentType


class DocumentService:
    """Coordinates document use cases without exposing repositories to routers."""

    def __init__(
        self,
        document_repository: DocumentRepository,
        parser: DocumentParserAgent = document_parser_agent,
    ) -> None:
        self.document_repository = document_repository
        self.parser = parser

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

    async def ingest_uploaded_document(
        self,
        *,
        document_id: str,
        project_id: str,
        document_type: DocumentType,
        file_name: str,
        storage_path: str,
        file_bytes: bytes,
    ) -> DocumentMetadata:
        document = await self.create_document(
            document_id=document_id,
            project_id=project_id,
            document_type=document_type,
            file_name=file_name,
            storage_path=storage_path,
        )

        parsed_document = await self.parser.parse(
            file_name=file_name,
            file_bytes=file_bytes,
        )
        if parsed_document is None:
            return document

        chunks = split_text_into_chunks(parsed_document.text)
        if not chunks:
            return document

        for chunk in chunks:
            await self.document_repository.create_chunk(
                chunk_id=f"CHUNK-{uuid4().hex[:12].upper()}",
                project_id=project_id,
                document_id=document_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                section_title=chunk.section_title,
                chunk_metadata={
                    **chunk.metadata,
                    "parser_name": parsed_document.parser_name,
                    "source_file_name": file_name,
                },
            )

        indexed_document = await self.document_repository.update_document_status(
            project_id=project_id,
            document_id=document_id,
            status=DocumentStatus.INDEXED,
        )
        return indexed_document or document

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
