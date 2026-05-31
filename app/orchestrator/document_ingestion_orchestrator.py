# EN: Orchestrates uploaded document ingestion flows.
# KO: 업로드 문서 수집/처리 흐름을 제어하는 Orchestrator입니다.

from uuid import uuid4

from app.agents.input_agents.document_parser_agent.agent import (
    DocumentParserAgent,
    document_parser_agent,
)
from app.rag.chunking import split_text_into_chunks
from app.repositories.document_repository import DocumentRepository
from app.schemas.artifact import DocumentMetadata, DocumentStatus, DocumentType
from app.schemas.io_agent import InputAgentRequest, InputFilePayload, InputType


class DocumentIngestionOrchestrator:
    """Coordinates parsing, chunking, persistence, and status transitions."""

    def __init__(
        self,
        parser: DocumentParserAgent = document_parser_agent,
    ) -> None:
        self.parser = parser

    async def ingest_uploaded_document(
        self,
        *,
        document_repository: DocumentRepository,
        document_id: str,
        project_id: str,
        document_type: DocumentType,
        file_name: str,
        storage_path: str,
        file_bytes: bytes,
    ) -> DocumentMetadata:
        document = await document_repository.create_document(
            document_id=document_id,
            project_id=project_id,
            document_type=document_type,
            file_name=file_name,
            storage_path=storage_path,
        )

        parsed_response = await self.parser.parse(
            InputAgentRequest(
                project_id=project_id,
                input_type=InputType.FILE,
                files=[
                    InputFilePayload(
                        file_name=file_name,
                        file_bytes=file_bytes,
                    )
                ],
                context={
                    "document_id": document_id,
                    "document_type": document_type.value,
                    "storage_path": storage_path,
                },
            )
        )
        if not parsed_response.success:
            return document

        parsed_text = str(parsed_response.structured_context.get("text", ""))
        parsed_metadata = parsed_response.structured_context.get("metadata", {})
        chunks = split_text_into_chunks(parsed_text)
        if not chunks:
            return document

        for chunk in chunks:
            await document_repository.create_chunk(
                chunk_id=f"CHUNK-{uuid4().hex[:12].upper()}",
                project_id=project_id,
                document_id=document_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                section_title=chunk.section_title,
                chunk_metadata={
                    **chunk.metadata,
                    **parsed_metadata,
                    "parser_name": parsed_response.agent_name,
                    "source_file_name": file_name,
                },
            )

        indexed_document = await document_repository.update_document_status(
            project_id=project_id,
            document_id=document_id,
            status=DocumentStatus.INDEXED,
        )
        return indexed_document or document


document_ingestion_orchestrator = DocumentIngestionOrchestrator()
