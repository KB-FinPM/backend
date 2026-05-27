import pytest

from app.orchestrator.generation_orchestrator import GenerationOrchestrator
from app.schemas.agent import AgentRequest, AgentResponse
from app.schemas.request import GenerationRequest


class StubRetrievalService:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.received_project_id: str | None = None
        self.received_query: str | None = None

    async def search(
        self,
        project_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        self.calls.append("retrieval")
        self.received_project_id = project_id
        self.received_query = query
        return [{"chunk_id": "CHUNK-001", "text": "Login is required."}]


class StubRequirementAgent:
    def __init__(self, calls: list[str], success: bool = True) -> None:
        self.calls = calls
        self.success = success
        self.received_request: AgentRequest | None = None

    async def generate(self, request: AgentRequest) -> AgentResponse:
        self.calls.append("requirement")
        self.received_request = request
        if not self.success:
            return AgentResponse(
                success=False,
                agent_name="RequirementAgent",
                error="requirement failed",
            )
        return AgentResponse(
            agent_name="RequirementAgent",
            result={"requirements": [{"id": "RQ-001"}]},
        )


class StubValidatorAgent:
    def __init__(self, calls: list[str], success: bool = True) -> None:
        self.calls = calls
        self.success = success
        self.received_result: dict | None = None

    async def validate(self, result: dict) -> AgentResponse:
        self.calls.append("validator")
        self.received_result = result
        if not self.success:
            return AgentResponse(
                success=False,
                agent_name="ValidatorAgent",
                error="validation failed",
            )
        return AgentResponse(
            agent_name="ValidatorAgent",
            result=result,
        )


@pytest.mark.anyio
async def test_generate_requirement_calls_retrieval_agent_and_validator() -> None:
    calls: list[str] = []
    retrieval = StubRetrievalService(calls)
    requirement = StubRequirementAgent(calls)
    validator = StubValidatorAgent(calls)
    orchestrator = GenerationOrchestrator(
        retrieval=retrieval,
        requirement_generator=requirement,
        validator=validator,
    )
    request = GenerationRequest(
        project_id="PRJ-001",
        document_ids=["DOC-001"],
        query="Create a requirement spec",
    )

    response = await orchestrator.generate_requirement(request)

    assert calls == ["retrieval", "requirement", "validator"]
    assert response.success is True
    assert response.project_id == "PRJ-001"
    assert response.result == {"requirements": [{"id": "RQ-001"}]}
    assert retrieval.received_project_id == "PRJ-001"
    assert retrieval.received_query == "Create a requirement spec"
    assert requirement.received_request is not None
    assert requirement.received_request.project_id == "PRJ-001"
    assert requirement.received_request.documents == [
        {"chunk_id": "CHUNK-001", "text": "Login is required."}
    ]
    assert requirement.received_request.context == {
        "document_ids": ["DOC-001"],
        "query": "Create a requirement spec",
    }
    assert validator.received_result == {"requirements": [{"id": "RQ-001"}]}


@pytest.mark.anyio
async def test_generate_requirement_stops_when_requirement_agent_fails() -> None:
    calls: list[str] = []
    orchestrator = GenerationOrchestrator(
        retrieval=StubRetrievalService(calls),
        requirement_generator=StubRequirementAgent(calls, success=False),
        validator=StubValidatorAgent(calls),
    )
    request = GenerationRequest(project_id="PRJ-001")

    response = await orchestrator.generate_requirement(request)

    assert calls == ["retrieval", "requirement"]
    assert response.success is False
    assert response.message == "requirement failed"
    assert response.result == {
        "agent_name": "RequirementAgent",
        "error": "requirement failed",
    }


@pytest.mark.anyio
async def test_generate_requirement_returns_validation_failure() -> None:
    calls: list[str] = []
    orchestrator = GenerationOrchestrator(
        retrieval=StubRetrievalService(calls),
        requirement_generator=StubRequirementAgent(calls),
        validator=StubValidatorAgent(calls, success=False),
    )
    request = GenerationRequest(project_id="PRJ-001")

    response = await orchestrator.generate_requirement(request)

    assert calls == ["retrieval", "requirement", "validator"]
    assert response.success is False
    assert response.message == "validation failed"
    assert response.result == {
        "agent_name": "ValidatorAgent",
        "error": "validation failed",
    }
