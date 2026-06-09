# EN: Tests for generation API routing behavior.
# KO: 산출물 생성 API 라우팅 동작을 검증하는 테스트입니다.

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
from app.schemas.io_agent import (
    InputAgentResponse,
    NormalizedRequestType,
    OutputAgentResponse,
)
from app.schemas.artifact import DocumentMetadata, DocumentType
from app.schemas.request import GenerationRequest
from app.schemas.response import GenerationResponse
from app.services.generation_service import GenerationSourceValidationResult


class StubGenerationOrchestrator:
    def __init__(self) -> None:
        self.received_request: GenerationRequest | None = None

    async def generate_artifact(
        self,
        request: GenerationRequest,
        artifact_service=None,
        retrieval_service=None,
        template_service=None,
        document_service=None,
    ) -> GenerationResponse:
        self.received_request = request
        return GenerationResponse(
            project_id=request.project_id,
            result={"source": "stub-orchestrator"},
        )

    async def validate_source_documents(
        self,
        request: GenerationRequest,
        *,
        document_service,
        required_source_type=None,
    ) -> GenerationSourceValidationResult:
        return GenerationSourceValidationResult(
            project_id=request.project_id,
            target_artifact_type=request.target_artifact_type,
            required_source_type=required_source_type,
        )


class StubInputOrchestrator:
    def __init__(self) -> None:
        self.received_input_type: str | None = None

    async def normalize(self, request):
        self.received_input_type = request.input_type
        return InputAgentResponse(
            agent_name="StubInputOrchestrator",
            normalized_request_type=NormalizedRequestType.ARTIFACT_GENERATION,
            structured_context={"normalized": True},
        )


class StubOutputOrchestrator:
    def __init__(self) -> None:
        self.received_response_type: str | None = None

    async def format(self, request):
        self.received_response_type = request.response_type
        return OutputAgentResponse(
            agent_name="StubOutputOrchestrator",
            display_payload={"formatted": True},
        )


class StubDocumentService:
    def __init__(
        self,
        documents: dict[str, DocumentMetadata] | None = None,
    ) -> None:
        self.documents = documents or {
            "DOC-001": DocumentMetadata(
                document_id="DOC-001",
                project_id="PRJ-001",
                document_type=DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION,
                file_name="construction-requirements.txt",
                storage_path="s3://bucket/DOC-001",
            ),
            "DOC-REQ-001": DocumentMetadata(
                document_id="DOC-REQ-001",
                project_id="PRJ-001",
                document_type=DocumentType.REQUIREMENT_SPEC,
                file_name="requirement-spec.txt",
                storage_path="s3://bucket/DOC-REQ-001",
            ),
        }

    async def get_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> DocumentMetadata | None:
        document = self.documents.get(document_id)
        if document is None or document.project_id != project_id:
            return None
        return document


def test_generate_requirement_delegates_to_orchestrator(
    client: TestClient,
) -> None:
    stub_generation_service = StubGenerationOrchestrator()
    stub_input_orchestrator = StubInputOrchestrator()
    stub_output_orchestrator = StubOutputOrchestrator()
    client.app.dependency_overrides[get_generation_service] = (
        lambda: stub_generation_service
    )
    client.app.dependency_overrides[get_artifact_service] = lambda: object()
    client.app.dependency_overrides[get_document_service] = lambda: StubDocumentService()
    client.app.dependency_overrides[get_retrieval_service] = lambda: object()
    client.app.dependency_overrides[get_template_service] = lambda: object()
    client.app.dependency_overrides[get_input_orchestrator] = (
        lambda: stub_input_orchestrator
    )
    client.app.dependency_overrides[get_output_orchestrator] = (
        lambda: stub_output_orchestrator
    )

    try:
        response = client.post(
            "/generate/requirement",
            json={
                "project_id": "PRJ-001",
                "source_document_ids": ["DOC-001"],
                "source_document_type": "CONSTRUCTION_REQUIREMENT_DEFINITION",
                "target_artifact_type": "REQUIREMENT_SPEC",
                "template_id": "TPL-REQ-SPEC-DEFAULT",
                "query": "Create a requirement spec",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["project_id"] == "PRJ-001"
    assert response.json()["result"]["source"] == "stub-orchestrator"
    assert response.json()["result"]["display"] == {"formatted": True}
    assert stub_input_orchestrator.received_input_type == "ARTIFACT_REQUEST"
    assert stub_output_orchestrator.received_response_type == "API_RESPONSE"
    assert stub_generation_service.received_request is not None
    assert stub_generation_service.received_request.source_document_ids == ["DOC-001"]
    assert stub_generation_service.received_request.document_ids == ["DOC-001"]
    assert stub_generation_service.received_request.template_id == (
        "TPL-REQ-SPEC-DEFAULT"
    )


def test_generate_wbs_sets_target_artifact_type(client: TestClient) -> None:
    stub_generation_service = StubGenerationOrchestrator()
    stub_input_orchestrator = StubInputOrchestrator()
    stub_output_orchestrator = StubOutputOrchestrator()
    client.app.dependency_overrides[get_generation_service] = (
        lambda: stub_generation_service
    )
    client.app.dependency_overrides[get_artifact_service] = lambda: object()
    client.app.dependency_overrides[get_document_service] = lambda: StubDocumentService()
    client.app.dependency_overrides[get_retrieval_service] = lambda: object()
    client.app.dependency_overrides[get_template_service] = lambda: object()
    client.app.dependency_overrides[get_input_orchestrator] = (
        lambda: stub_input_orchestrator
    )
    client.app.dependency_overrides[get_output_orchestrator] = (
        lambda: stub_output_orchestrator
    )

    try:
        response = client.post(
            "/generate/wbs",
            json={
                "project_id": "PRJ-001",
                "source_document_ids": ["DOC-REQ-001"],
                "source_document_type": "REQUIREMENT_SPEC",
                "target_artifact_type": "REQUIREMENT_SPEC",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert stub_generation_service.received_request is not None
    assert stub_generation_service.received_request.target_artifact_type == "WBS"
    assert stub_input_orchestrator.received_input_type == "ARTIFACT_REQUEST"
    assert stub_output_orchestrator.received_response_type == "API_RESPONSE"


def test_generate_screen_design_sets_target_artifact_type(client: TestClient) -> None:
    stub_generation_service = StubGenerationOrchestrator()
    stub_input_orchestrator = StubInputOrchestrator()
    stub_output_orchestrator = StubOutputOrchestrator()
    client.app.dependency_overrides[get_generation_service] = (
        lambda: stub_generation_service
    )
    client.app.dependency_overrides[get_artifact_service] = lambda: object()
    client.app.dependency_overrides[get_document_service] = lambda: StubDocumentService()
    client.app.dependency_overrides[get_retrieval_service] = lambda: object()
    client.app.dependency_overrides[get_template_service] = lambda: object()
    client.app.dependency_overrides[get_input_orchestrator] = (
        lambda: stub_input_orchestrator
    )
    client.app.dependency_overrides[get_output_orchestrator] = (
        lambda: stub_output_orchestrator
    )

    try:
        response = client.post(
            "/generate/screen-design",
            json={
                "project_id": "PRJ-001",
                "source_document_ids": ["DOC-REQ-001"],
                "source_document_type": "REQUIREMENT_SPEC",
                "target_artifact_type": "REQUIREMENT_SPEC",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert stub_generation_service.received_request is not None
    assert stub_generation_service.received_request.target_artifact_type == (
        "SCREEN_DESIGN"
    )
    assert stub_input_orchestrator.received_input_type == "ARTIFACT_REQUEST"
    assert stub_output_orchestrator.received_response_type == "API_RESPONSE"


def test_generate_wbs_returns_404_when_source_document_is_missing(
    client: TestClient,
) -> None:
    client.app.dependency_overrides[get_document_service] = lambda: StubDocumentService(
        documents={}
    )

    try:
        response = client.post(
            "/generate/wbs",
            json={
                "project_id": "PRJ-001",
                "source_document_ids": ["DOC-MISSING"],
                "source_document_type": "REQUIREMENT_SPEC",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "SOURCE_DOCUMENT_NOT_FOUND"
    assert body["detail"]["missing_document_ids"] == ["DOC-MISSING"]


def test_generate_screen_design_rejects_non_requirement_spec_source(
    client: TestClient,
) -> None:
    client.app.dependency_overrides[get_document_service] = lambda: StubDocumentService()

    try:
        response = client.post(
            "/generate/screen-design",
            json={
                "project_id": "PRJ-001",
                "source_document_ids": ["DOC-001"],
                "source_document_type": "CONSTRUCTION_REQUIREMENT_DEFINITION",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "INVALID_SOURCE_DOCUMENT_TYPE"


def test_generate_action_items_route_is_not_exposed(client: TestClient) -> None:
    response = client.post(
        "/generate/action-items",
        json={
            "project_id": "PRJ-001",
            "source_document_ids": ["DOC-001"],
        },
    )

    assert response.status_code == 404
