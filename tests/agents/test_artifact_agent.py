# EN: Tests for unified artifact agent dispatch behavior.
# KO: 통합 산출물 Agent dispatch 동작 테스트입니다.

import pytest

from app.agents.core_agents.artifact_agent.agent import ArtifactAgent
from app.schemas.agent import AgentRequest, AgentResponse


class StubGenerator:
    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name
        self.received_request: AgentRequest | None = None

    async def generate(self, request: AgentRequest) -> AgentResponse:
        self.received_request = request
        return AgentResponse(
            agent_name=self.agent_name,
            result={"source": self.agent_name},
        )


@pytest.mark.anyio
async def test_artifact_agent_dispatches_requirement_generation() -> None:
    requirement = StubGenerator("RequirementAgent")
    agent = ArtifactAgent(requirement_generator=requirement)

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={"target_artifact_type": "REQUIREMENT_SPEC"},
        )
    )

    assert response.result == {"source": "RequirementAgent"}
    assert requirement.received_request is not None


@pytest.mark.anyio
async def test_artifact_agent_dispatches_wbs_generation() -> None:
    wbs = StubGenerator("WbsAgent")
    agent = ArtifactAgent(wbs_generator=wbs)

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={"target_artifact_type": "WBS"},
        )
    )

    assert response.result == {"source": "WbsAgent"}
    assert wbs.received_request is not None


@pytest.mark.anyio
async def test_artifact_agent_dispatches_screen_design_generation() -> None:
    screen_design = StubGenerator("ScreenDesignAgent")
    agent = ArtifactAgent(screen_design_generator=screen_design)

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={"target_artifact_type": "SCREEN_DESIGN"},
        )
    )

    assert response.result == {"source": "ScreenDesignAgent"}
    assert screen_design.received_request is not None


@pytest.mark.anyio
async def test_artifact_agent_dispatches_unit_test_generation() -> None:
    unit_test = StubGenerator("UnitTestAgent")
    agent = ArtifactAgent(unit_test_generator=unit_test)

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={"target_artifact_type": "UNITTEST_SPEC"},
        )
    )

    assert response.result == {"source": "UnitTestAgent"}
    assert unit_test.received_request is not None
