# EN: Tests for WBS agent input validation behavior.
# KO: WBS Agent 입력 검증 동작 테스트입니다.

import pytest

from app.agents.core_agents.wbs_agent.agent import WbsAgent
from app.schemas.agent import AgentRequest


@pytest.mark.anyio
async def test_wbs_agent_requires_requirement_context() -> None:
    agent = WbsAgent()

    response = await agent.generate(AgentRequest(project_id="PRJ-001"))

    assert response.success is False
    assert response.agent_name == "WbsAgent"
    assert response.error == "No requirement context available for WBS generation"
