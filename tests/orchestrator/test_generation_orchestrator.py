import pytest

from app.orchestrator.generation_orchestrator import GenerationOrchestrator
from app.schemas.request import GenerationRequest


@pytest.mark.anyio
async def test_generate_requirement_returns_project_scoped_response() -> None:
    orchestrator = GenerationOrchestrator()
    request = GenerationRequest(
        project_id="PRJ-001",
        document_ids=["DOC-001"],
        query="Create a requirement spec",
    )

    response = await orchestrator.generate_requirement(request)

    assert response.success is True
    assert response.project_id == "PRJ-001"
    assert "mock" in response.result
