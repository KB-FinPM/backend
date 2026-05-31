# EN: Tests for generation service orchestration boundary.
# KO: 생성 서비스의 오케스트레이터 위임 경계 테스트입니다.

import pytest

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
    ) -> GenerationResponse:
        self.received_request = request
        self.received_artifact_service = artifact_service
        return GenerationResponse(
            project_id=request.project_id,
            result={"source": "stub-orchestrator"},
        )


@pytest.mark.anyio
async def test_generation_service_delegates_requirement_flow() -> None:
    orchestrator = StubOrchestrator()
    artifact_service = object()
    service = GenerationService(orchestrator)
    request = GenerationRequest(project_id="PRJ-001")

    response = await service.generate_requirement(
        request,
        artifact_service=artifact_service,
    )

    assert response.result == {"source": "stub-orchestrator"}
    assert orchestrator.received_request == request
    assert orchestrator.received_artifact_service is artifact_service
