from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.schemas.request import GenerationRequest
from app.schemas.response import GenerationResponse


class StubGenerationOrchestrator:
    def __init__(self) -> None:
        self.received_request: GenerationRequest | None = None

    async def generate_requirement(
        self,
        request: GenerationRequest,
    ) -> GenerationResponse:
        self.received_request = request
        return GenerationResponse(
            project_id=request.project_id,
            result={"source": "stub-orchestrator"},
        )


def test_generate_requirement_delegates_to_orchestrator(
    client: TestClient,
    monkeypatch: MonkeyPatch,
) -> None:
    stub_orchestrator = StubGenerationOrchestrator()
    monkeypatch.setattr(
        "app.api.generation.generation_orchestrator",
        stub_orchestrator,
    )

    response = client.post(
        "/generate/requirement",
        json={
            "project_id": "PRJ-001",
            "document_ids": ["DOC-001"],
            "query": "Create a requirement spec",
        },
    )

    assert response.status_code == 200
    assert response.json()["project_id"] == "PRJ-001"
    assert response.json()["result"] == {"source": "stub-orchestrator"}
    assert stub_orchestrator.received_request is not None
    assert stub_orchestrator.received_request.document_ids == ["DOC-001"]
