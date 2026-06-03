# EN: Tests for document service delegation behavior.
# KO: 문서 서비스 위임 동작 테스트입니다.

import pytest

from app.schemas.artifact import DocumentMetadata, DocumentType
from app.services.document_service import DocumentService


class StubDocumentRepository:
    pass


class StubIngestionOrchestrator:
    def __init__(self) -> None:
        self.received_document_repository = None
        self.received_file_bytes: bytes | None = None
        self.received_parsed_context: dict | None = None

    async def ingest_uploaded_document(
        self,
        *,
        document_repository,
        document_id: str,
        project_id: str,
        document_type: DocumentType,
        file_name: str,
        storage_path: str,
        file_bytes: bytes,
        parsed_context: dict | None = None,
    ) -> DocumentMetadata:
        self.received_document_repository = document_repository
        self.received_file_bytes = file_bytes
        self.received_parsed_context = parsed_context
        return DocumentMetadata(
            document_id=document_id,
            project_id=project_id,
            document_type=document_type,
            file_name=file_name,
            storage_path=storage_path,
        )


@pytest.mark.anyio
async def test_document_service_delegates_ingestion_to_orchestrator() -> None:
    repository = StubDocumentRepository()
    orchestrator = StubIngestionOrchestrator()
    service = DocumentService(repository, ingestion_orchestrator=orchestrator)

    document = await service.ingest_uploaded_document(
        document_id="DOC-001",
        project_id="PRJ-001",
        document_type=DocumentType.REQUIREMENT_SPEC,
        file_name="requirements.txt",
        storage_path="s3://bucket/requirements.txt",
        file_bytes=b"requirements",
    )

    assert document.document_id == "DOC-001"
    assert orchestrator.received_document_repository is repository
    assert orchestrator.received_file_bytes == b"requirements"
    assert orchestrator.received_parsed_context is None
