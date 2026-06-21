from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    get_artifact_service,
    get_document_service,
    get_generation_service,
    get_input_orchestrator,
    get_output_orchestrator,
    get_retrieval_service,
    get_template_service,
)
from app.schemas.artifact import DocumentMetadata, DocumentType
from app.schemas.io_agent import InputAgentResponse, NormalizedRequestType, OutputAgentResponse
from app.schemas.response import GenerationResponse
from app.services.generation_service import GenerationSourceValidationResult


class SpyGenerationService:
    def __init__(
        self,
        *,
        validation_result: GenerationSourceValidationResult | None = None,
        generation_response: GenerationResponse | None = None,
    ) -> None:
        self.validation_result = validation_result
        self.generation_response = generation_response
        self.received_request = None
        self.generate_called = False

    async def validate_source_documents(self, request, *, document_service, required_source_type=None):
        if self.validation_result is not None:
            return self.validation_result
        return GenerationSourceValidationResult(
            project_id=request.project_id,
            target_artifact_type=request.target_artifact_type,
            required_source_type=required_source_type,
        )

    async def generate_artifact(self, request, **kwargs):
        self.generate_called = True
        self.received_request = request
        if self.generation_response is not None:
            return self.generation_response
        return GenerationResponse(
            project_id=request.project_id,
            result={"generated": {"artifact_type": request.target_artifact_type.value}},
        )


class StubDocumentService:
    async def get_document(self, *, project_id: str, document_id: str):
        return DocumentMetadata(
            document_id=document_id,
            project_id=project_id,
            document_type=DocumentType.REQUIREMENT_SPEC,
            file_name="requirement.xlsx",
            storage_path="mock://requirement.xlsx",
        )


class SpyInputOrchestrator:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.called = False

    async def normalize(self, request):
        self.called = True
        if self.fail:
            return InputAgentResponse(
                success=False,
                agent_name="SpyInputOrchestrator",
                normalized_request_type=NormalizedRequestType.UNKNOWN,
                error="bad input",
                validation_errors=["bad input"],
            )
        return InputAgentResponse(
            agent_name="SpyInputOrchestrator",
            normalized_request_type=NormalizedRequestType.ARTIFACT_GENERATION,
            structured_context={"ok": True},
        )


class StubOutputOrchestrator:
    async def format(self, request):
        return OutputAgentResponse(
            agent_name="StubOutputOrchestrator",
            display_payload={"formatted": True},
        )


def _install_generation_fakes(
    client: TestClient,
    generation_service: SpyGenerationService,
    input_orchestrator: SpyInputOrchestrator,
) -> None:
    client.app.dependency_overrides[get_generation_service] = lambda: generation_service
    client.app.dependency_overrides[get_document_service] = lambda: StubDocumentService()
    client.app.dependency_overrides[get_input_orchestrator] = lambda: input_orchestrator
    client.app.dependency_overrides[get_output_orchestrator] = lambda: StubOutputOrchestrator()
    client.app.dependency_overrides[get_artifact_service] = lambda: object()
    client.app.dependency_overrides[get_retrieval_service] = lambda: object()
    client.app.dependency_overrides[get_template_service] = lambda: object()


@pytest.mark.parametrize("start_date", ["2024-99-99", "2024/1/1", "tomorrow"])
def test_generation_start_date_validation_error_skips_generation(
    client: TestClient,
    start_date: str,
) -> None:
    generation_service = SpyGenerationService()
    input_orchestrator = SpyInputOrchestrator()
    _install_generation_fakes(client, generation_service, input_orchestrator)

    try:
        response = client.post(
            "/api/generate/wbs",
            json={
                "project_id": "PRJ-001",
                "source_document_ids": ["DOC-REQ"],
                "start_date": start_date,
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"
    assert generation_service.generate_called is False
    assert input_orchestrator.called is False


def test_generation_document_ids_alias_reaches_downstream_request(client: TestClient) -> None:
    generation_service = SpyGenerationService()
    input_orchestrator = SpyInputOrchestrator()
    _install_generation_fakes(client, generation_service, input_orchestrator)

    try:
        response = client.post(
            "/api/generate/wbs",
            json={
                "project_id": "PRJ-001",
                "document_ids": ["DOC-REQ"],
                "target_artifact_type": "REQUIREMENT_SPEC",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert generation_service.received_request.source_document_ids == ["DOC-REQ"]
    assert generation_service.received_request.document_ids == ["DOC-REQ"]
    assert generation_service.received_request.target_artifact_type == "WBS"


def test_source_validation_failure_skips_input_and_generation(client: TestClient) -> None:
    generation_service = SpyGenerationService(
        validation_result=GenerationSourceValidationResult(
            project_id="PRJ-001",
            target_artifact_type="WBS",
            missing_document_ids=["DOC-MISSING"],
        )
    )
    input_orchestrator = SpyInputOrchestrator()
    _install_generation_fakes(client, generation_service, input_orchestrator)

    try:
        response = client.post(
            "/api/generate/wbs",
            json={"project_id": "PRJ-001", "source_document_ids": ["DOC-MISSING"]},
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["error_code"] == "SOURCE_DOCUMENT_NOT_FOUND"
    assert input_orchestrator.called is False
    assert generation_service.generate_called is False


def test_input_normalization_failure_skips_generation(client: TestClient) -> None:
    generation_service = SpyGenerationService()
    input_orchestrator = SpyInputOrchestrator(fail=True)
    _install_generation_fakes(client, generation_service, input_orchestrator)

    try:
        response = client.post(
            "/api/generate/wbs",
            json={"project_id": "PRJ-001", "source_document_ids": ["DOC-REQ"]},
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["error_code"] == "GENERATION_INPUT_NORMALIZATION_FAILED"
    assert generation_service.generate_called is False


def test_generation_failure_returns_structured_422_without_traceback(
    client: TestClient,
) -> None:
    generation_service = SpyGenerationService(
        generation_response=GenerationResponse(
            success=False,
            project_id="PRJ-001",
            message="validation failed",
            result={"reason": "invalid artifact"},
        )
    )
    input_orchestrator = SpyInputOrchestrator()
    _install_generation_fakes(client, generation_service, input_orchestrator)

    try:
        response = client.post(
            "/api/generate/wbs",
            json={"project_id": "PRJ-001", "source_document_ids": ["DOC-REQ"]},
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["error_code"] == "GENERATION_FAILED"
    assert "traceback" not in response.text.lower()
