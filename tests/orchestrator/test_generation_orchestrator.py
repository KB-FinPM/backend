# EN: Tests for generation orchestrator flow coordination.
# KO: 산출물 생성 오케스트레이터의 흐름 제어를 검증하는 테스트입니다.

import pytest

from app.orchestrator.generation_orchestrator import GenerationOrchestrator
from app.schemas.agent import AgentRequest, AgentResponse
from app.schemas.artifact import ArtifactMetadata, ArtifactType
from app.schemas.request import GenerationRequest
from app.schemas.template import TemplateMetadata


class StubRetrievalService:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.received_project_id: str | None = None
        self.received_permission_scope: list[str] | None = None
        self.received_query: str | None = None

    async def search(
        self,
        project_id: str,
        permission_scope: list[str],
        query: str,
        top_k: int = 5,
        document_ids: list[str] | None = None,
    ) -> list[dict]:
        self.calls.append("retrieval")
        self.received_project_id = project_id
        self.received_permission_scope = permission_scope
        self.received_query = query
        self.received_document_ids = document_ids
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


class StubPlaceholderAgent:
    def __init__(self, calls: list[str], agent_name: str, error: str) -> None:
        self.calls = calls
        self.agent_name = agent_name
        self.error = error
        self.received_request: AgentRequest | None = None

    async def generate(self, request: AgentRequest) -> AgentResponse:
        self.calls.append(self.agent_name)
        self.received_request = request
        return AgentResponse(
            success=False,
            agent_name=self.agent_name,
            error=self.error,
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


class StubArtifactService:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.received_source_document_ids: list[str] | None = None
        self.received_result_json: dict | None = None

    async def create_artifact(
        self,
        *,
        artifact_id: str,
        project_id: str,
        artifact_type: ArtifactType,
        name: str,
        source_document_ids: list[str],
        result_json: dict,
        template_id: str | None = None,
        template_version: str | None = None,
        storage_path: str | None = None,
    ) -> ArtifactMetadata:
        self.calls.append("artifact")
        self.received_source_document_ids = source_document_ids
        self.received_result_json = result_json
        return ArtifactMetadata(
            artifact_id=artifact_id,
            project_id=project_id,
            artifact_type=artifact_type,
            name=name,
            source_document_ids=source_document_ids,
            template_id=template_id,
            template_version=template_version,
            result_json=result_json,
            storage_path=storage_path,
        )


class StubTemplateService:
    def __init__(self, template: TemplateMetadata | None) -> None:
        self.template = template

    async def resolve_template(
        self,
        *,
        reference,
        artifact_type: ArtifactType,
    ) -> TemplateMetadata | None:
        return self.template


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
        source_document_ids=["DOC-001"],
        source_document_type="CONSTRUCTION_REQUIREMENT_DEFINITION",
        target_artifact_type="REQUIREMENT_SPEC",
        template_id="TPL-REQ-SPEC-DEFAULT",
        template_version="v1",
        query="Create a requirement spec",
        permission_scope=["project:read", "artifact:generate"],
    )

    response = await orchestrator.generate_requirement(request)

    assert calls == ["retrieval", "requirement", "validator"]
    assert response.success is True
    assert response.project_id == "PRJ-001"
    assert response.result == {"requirements": [{"id": "RQ-001"}]}
    assert retrieval.received_project_id == "PRJ-001"
    assert retrieval.received_permission_scope == [
        "project:read",
        "artifact:generate",
    ]
    assert retrieval.received_query == ""
    assert retrieval.received_document_ids == ["DOC-001"]
    assert requirement.received_request is not None
    assert requirement.received_request.project_id == "PRJ-001"
    assert requirement.received_request.documents == [
        {"chunk_id": "CHUNK-001", "text": "Login is required."}
    ]
    assert requirement.received_request.context is not None
    assert requirement.received_request.context["source_document_ids"] == ["DOC-001"]
    assert requirement.received_request.context["document_ids"] == ["DOC-001"]
    assert requirement.received_request.context["source_document_type"] == (
        "CONSTRUCTION_REQUIREMENT_DEFINITION"
    )
    assert requirement.received_request.context["target_artifact_type"] == (
        "REQUIREMENT_SPEC"
    )
    assert requirement.received_request.context["template"] == {
        "template_id": "TPL-REQ-SPEC-DEFAULT",
        "template_version": "v1",
    }
    assert requirement.received_request.context["query"] == "Create a requirement spec"
    assert requirement.received_request.context["permission_scope"] == [
        "project:read",
        "artifact:generate",
    ]
    assert requirement.received_request.context["generation_orchestrator"] is (
        orchestrator
    )
    assert validator.received_result == {"requirements": [{"id": "RQ-001"}]}


@pytest.mark.anyio
async def test_generate_artifact_dispatches_requirement_flow() -> None:
    calls: list[str] = []
    orchestrator = GenerationOrchestrator(
        retrieval=StubRetrievalService(calls),
        requirement_generator=StubRequirementAgent(calls),
        validator=StubValidatorAgent(calls),
    )
    request = GenerationRequest(
        project_id="PRJ-001",
        target_artifact_type="REQUIREMENT_SPEC",
    )

    response = await orchestrator.generate_artifact(request)

    assert response.success is True
    assert calls == ["retrieval", "requirement", "validator"]


@pytest.mark.anyio
async def test_generate_artifact_dispatches_wbs_agent_adapter() -> None:
    calls: list[str] = []
    wbs_agent = StubPlaceholderAgent(
        calls,
        agent_name="WbsAgent",
        error="WBS generation agent is not implemented yet",
    )
    orchestrator = GenerationOrchestrator(
        retrieval=StubRetrievalService(calls),
        requirement_generator=StubRequirementAgent(calls),
        wbs_generator=wbs_agent,
        validator=StubValidatorAgent(calls),
    )
    request = GenerationRequest(
        project_id="PRJ-001",
        target_artifact_type="WBS",
        start_date="2024-01-10",
        project_period="6개월",
    )

    response = await orchestrator.generate_artifact(request)

    assert response.success is False
    assert response.message == "WBS generation agent is not implemented yet"
    assert response.result == {
        "agent_name": "WbsAgent",
        "error": "WBS generation agent is not implemented yet",
    }
    assert calls == ["retrieval", "WbsAgent"]
    assert wbs_agent.received_request is not None
    assert wbs_agent.received_request.context["target_artifact_type"] == "WBS"
    assert wbs_agent.received_request.context["start_date"] == "2024-01-10"
    assert wbs_agent.received_request.context["project_period"] == "6개월"


@pytest.mark.anyio
async def test_generate_artifact_dispatches_screen_design_agent_adapter() -> None:
    calls: list[str] = []
    screen_design_agent = StubPlaceholderAgent(
        calls,
        agent_name="ScreenDesignAgent",
        error="Screen design generation agent is not implemented yet",
    )
    orchestrator = GenerationOrchestrator(
        retrieval=StubRetrievalService(calls),
        requirement_generator=StubRequirementAgent(calls),
        screen_design_generator=screen_design_agent,
        validator=StubValidatorAgent(calls),
    )
    request = GenerationRequest(
        project_id="PRJ-001",
        target_artifact_type="SCREEN_DESIGN",
    )

    response = await orchestrator.generate_artifact(request)

    assert response.success is False
    assert response.message == "Screen design generation agent is not implemented yet"
    assert calls == ["retrieval", "ScreenDesignAgent"]
    assert screen_design_agent.received_request is not None
    assert screen_design_agent.received_request.context["target_artifact_type"] == (
        "SCREEN_DESIGN"
    )


@pytest.mark.anyio
async def test_generate_artifact_dispatches_unit_test_agent_adapter() -> None:
    calls: list[str] = []
    unit_test_agent = StubPlaceholderAgent(
        calls,
        agent_name="UnitTestAgent",
        error="Unit test generation agent is not implemented yet",
    )
    orchestrator = GenerationOrchestrator(
        retrieval=StubRetrievalService(calls),
        requirement_generator=StubRequirementAgent(calls),
        unit_test_generator=unit_test_agent,
        validator=StubValidatorAgent(calls),
    )
    request = GenerationRequest(
        project_id="PRJ-001",
        target_artifact_type="UNITTEST_SPEC",
    )

    response = await orchestrator.generate_artifact(request)

    assert response.success is False
    assert response.message == "Unit test generation agent is not implemented yet"
    assert calls == ["retrieval", "UnitTestAgent"]
    assert unit_test_agent.received_request is not None
    assert unit_test_agent.received_request.context["target_artifact_type"] == (
        "UNITTEST_SPEC"
    )
    assert unit_test_agent.received_request.context["generation_orchestrator"] is (
        orchestrator
    )


@pytest.mark.anyio
async def test_generate_requirement_adds_resolved_template_to_agent_context() -> None:
    calls: list[str] = []
    requirement = StubRequirementAgent(calls)
    template = TemplateMetadata(
        template_id="TPL-REQ-SPEC-DEFAULT",
        template_version="v1",
        artifact_type=ArtifactType.REQUIREMENT_SPEC,
        name="Default Requirement Specification",
        content="Generate requirements.",
        is_builtin=True,
    )
    orchestrator = GenerationOrchestrator(
        retrieval=StubRetrievalService(calls),
        requirement_generator=requirement,
        validator=StubValidatorAgent(calls),
    )
    request = GenerationRequest(
        project_id="PRJ-001",
        target_artifact_type="REQUIREMENT_SPEC",
    )

    response = await orchestrator.generate_requirement(
        request,
        template_service=StubTemplateService(template),
    )

    assert response.success is True
    assert requirement.received_request is not None
    assert requirement.received_request.context["template"]["template_id"] == (
        "TPL-REQ-SPEC-DEFAULT"
    )
    assert requirement.received_request.context["template"]["content"] == (
        "Generate requirements."
    )


@pytest.mark.anyio
async def test_generate_requirement_fails_when_requested_template_is_missing() -> None:
    calls: list[str] = []
    orchestrator = GenerationOrchestrator(
        retrieval=StubRetrievalService(calls),
        requirement_generator=StubRequirementAgent(calls),
        validator=StubValidatorAgent(calls),
    )
    request = GenerationRequest(
        project_id="PRJ-001",
        template_id="missing",
    )

    response = await orchestrator.generate_requirement(
        request,
        template_service=StubTemplateService(None),
    )

    assert response.success is False
    assert response.message == "template not found"
    assert calls == []


@pytest.mark.anyio
async def test_generate_requirement_persists_validated_artifact() -> None:
    calls: list[str] = []
    artifact_service = StubArtifactService(calls)
    orchestrator = GenerationOrchestrator(
        retrieval=StubRetrievalService(calls),
        requirement_generator=StubRequirementAgent(calls),
        validator=StubValidatorAgent(calls),
    )
    request = GenerationRequest(
        project_id="PRJ-001",
        source_document_ids=["DOC-001"],
        target_artifact_type="REQUIREMENT_SPEC",
    )

    response = await orchestrator.generate_requirement(
        request,
        artifact_service=artifact_service,
    )

    assert calls == ["retrieval", "requirement", "validator", "artifact"]
    assert response.success is True
    assert response.message == "artifact generated"
    assert response.result["artifact"]["artifact_id"].startswith("ART-")
    assert response.result["artifact"]["project_id"] == "PRJ-001"
    assert response.result["generated"] == {"requirements": [{"id": "RQ-001"}]}
    assert artifact_service.received_source_document_ids == ["DOC-001"]
    assert artifact_service.received_result_json == {"requirements": [{"id": "RQ-001"}]}


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
