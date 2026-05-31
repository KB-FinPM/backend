# EN: Tests for generation API routing behavior.
# KO: 산출물 생성 API 라우팅 동작을 검증하는 테스트입니다.

from fastapi.testclient import TestClient

from app.dependencies import (
    get_artifact_service,
    get_generation_service,
    get_retrieval_service,
    get_template_service,
)
from app.schemas.request import GenerationRequest
from app.schemas.response import GenerationResponse


class StubGenerationOrchestrator:
    def __init__(self) -> None:
        self.received_request: GenerationRequest | None = None

    async def generate_artifact(
        self,
        request: GenerationRequest,
        artifact_service=None,
        retrieval_service=None,
        template_service=None,
    ) -> GenerationResponse:
        self.received_request = request
        return GenerationResponse(
            project_id=request.project_id,
            result={"source": "stub-orchestrator"},
        )


def test_generate_requirement_delegates_to_orchestrator(
    client: TestClient,
) -> None:
    stub_generation_service = StubGenerationOrchestrator()
    client.app.dependency_overrides[get_generation_service] = (
        lambda: stub_generation_service
    )
    client.app.dependency_overrides[get_artifact_service] = lambda: object()
    client.app.dependency_overrides[get_retrieval_service] = lambda: object()
    client.app.dependency_overrides[get_template_service] = lambda: object()

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
    assert response.json()["result"] == {"source": "stub-orchestrator"}
    assert stub_generation_service.received_request is not None
    assert stub_generation_service.received_request.source_document_ids == ["DOC-001"]
    assert stub_generation_service.received_request.document_ids == ["DOC-001"]
    assert stub_generation_service.received_request.template_id == (
        "TPL-REQ-SPEC-DEFAULT"
    )


def test_generate_wbs_sets_target_artifact_type(client: TestClient) -> None:
    stub_generation_service = StubGenerationOrchestrator()
    client.app.dependency_overrides[get_generation_service] = (
        lambda: stub_generation_service
    )
    client.app.dependency_overrides[get_artifact_service] = lambda: object()
    client.app.dependency_overrides[get_retrieval_service] = lambda: object()
    client.app.dependency_overrides[get_template_service] = lambda: object()

    try:
        response = client.post(
            "/generate/wbs",
            json={
                "project_id": "PRJ-001",
                "target_artifact_type": "REQUIREMENT_SPEC",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert stub_generation_service.received_request is not None
    assert stub_generation_service.received_request.target_artifact_type == "WBS"


def test_generate_screen_design_sets_target_artifact_type(client: TestClient) -> None:
    stub_generation_service = StubGenerationOrchestrator()
    client.app.dependency_overrides[get_generation_service] = (
        lambda: stub_generation_service
    )
    client.app.dependency_overrides[get_artifact_service] = lambda: object()
    client.app.dependency_overrides[get_retrieval_service] = lambda: object()
    client.app.dependency_overrides[get_template_service] = lambda: object()

    try:
        response = client.post(
            "/generate/screen-design",
            json={
                "project_id": "PRJ-001",
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
