# EN: Tests for WBS agent adapter placeholder behavior.
# KO: WBS Agent adapter placeholder 동작 테스트입니다.

import pytest

from app.agents.core_agents.wbs_agent.agent import WbsAgent
from app.schemas.agent import AgentRequest


@pytest.mark.anyio
async def test_wbs_agent_returns_not_implemented_until_source_is_delivered() -> None:
    agent = WbsAgent()

    response = await agent.generate(AgentRequest(project_id="PRJ-001"))

    assert response.success is False
    assert response.agent_name == "WbsAgent"
    assert response.error == "WBS generation agent is not implemented yet"
