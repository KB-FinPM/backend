# EN: Tests for generation service orchestration boundary.
# KO: 생성 서비스의 오케스트레이터 위임 경계 테스트입니다.

import pytest

from app.schemas.artifact import DocumentMetadata, DocumentType
from app.schemas.request import GenerationRequest
from app.schemas.response import GenerationResponse
from app.services.generation_service import GenerationService


class StubOrchestrator:
    def __init__(self) -> None:
        self.received_request: GenerationRequest | None = None
        self.received_artifact_service = None

    async def generate_requirement(
        self,
        request: GenerationRequest,
        artifact_service=None,
        retrieval_service=None,
        template_service=None,
    ) -> GenerationResponse:
        self.received_request = request
        self.received_artifact_service = artifact_service
        self.received_retrieval_service = retrieval_service
        self.received_template_service = template_service
        return GenerationResponse(
            project_id=request.project_id,
            result={"source": "stub-orchestrator"},
        )

    async def generate_artifact(
        self,
        request: GenerationRequest,
        artifact_service=None,
        retrieval_service=None,
        template_service=None,
    ) -> GenerationResponse:
        self.received_request = request
        self.received_artifact_service = artifact_service
        self.received_retrieval_service = retrieval_service
        self.received_template_service = template_service
        return GenerationResponse(
            project_id=request.project_id,
            result={"source": "stub-dispatch"},
        )


class StubDocumentService:
    def __init__(self, documents=None) -> None:
        self.documents = documents or {}

    async def get_document(self, *, project_id: str, document_id: str):
        document = self.documents.get(document_id)
        if document is None or document.project_id != project_id:
            return None
        return document


@pytest.mark.anyio
async def test_generation_service_delegates_requirement_flow() -> None:
    orchestrator = StubOrchestrator()
    artifact_service = object()
    retrieval_service = object()
    template_service = object()
    service = GenerationService(orchestrator)
    request = GenerationRequest(project_id="PRJ-001")

    response = await service.generate_requirement(
        request,
        artifact_service=artifact_service,
        retrieval_service=retrieval_service,
        template_service=template_service,
    )

    assert response.result == {"source": "stub-orchestrator"}
    assert orchestrator.received_request == request
    assert orchestrator.received_artifact_service is artifact_service
    assert orchestrator.received_retrieval_service is retrieval_service
    assert orchestrator.received_template_service is template_service


@pytest.mark.anyio
async def test_generation_service_delegates_artifact_dispatch() -> None:
    orchestrator = StubOrchestrator()
    artifact_service = object()
    service = GenerationService(orchestrator)
    request = GenerationRequest(project_id="PRJ-001", target_artifact_type="WBS")

    response = await service.generate_artifact(
        request,
        artifact_service=artifact_service,
    )

    assert response.result == {"source": "stub-dispatch"}
    assert orchestrator.received_request == request
    assert orchestrator.received_artifact_service is artifact_service


@pytest.mark.anyio
async def test_generation_service_validates_missing_source_documents() -> None:
    service = GenerationService(StubOrchestrator())
    request = GenerationRequest(
        project_id="PRJ-001",
        source_document_ids=["DOC-MISSING"],
        target_artifact_type="WBS",
    )

    result = await service.validate_source_documents(
        request,
        document_service=StubDocumentService(),
    )

    assert result.success is False
    assert result.error_code == "SOURCE_DOCUMENT_NOT_FOUND"
    assert result.detail == {
        "project_id": "PRJ-001",
        "missing_document_ids": ["DOC-MISSING"],
    }


@pytest.mark.anyio
async def test_generation_service_validates_required_source_type() -> None:
    service = GenerationService(StubOrchestrator())
    document = DocumentMetadata(
        document_id="DOC-001",
        project_id="PRJ-001",
        document_type=DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION,
        file_name="definition.txt",
        storage_path="s3://bucket/definition.txt",
    )
    request = GenerationRequest(
        project_id="PRJ-001",
        source_document_ids=["DOC-001"],
        target_artifact_type="WBS",
    )

    result = await service.validate_source_documents(
        request,
        document_service=StubDocumentService({"DOC-001": document}),
    )

    assert result.success is False
    assert result.error_code == "INVALID_SOURCE_DOCUMENT_TYPE"
    assert result.detail == {
        "documents": [
            {
                "document_id": "DOC-001",
                "document_type": "CONSTRUCTION_REQUIREMENT_DEFINITION",
                "required_document_type": "REQUIREMENT_SPEC",
            }
        ]
    }
