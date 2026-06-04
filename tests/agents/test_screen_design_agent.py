# EN: Tests for screen design agent adapter placeholder behavior.
# KO: 화면설계 Agent adapter placeholder 동작 테스트입니다.

import pytest

from app.agents.core_agents.screen_design_agent.agent import ScreenDesignAgent
from app.schemas.agent import AgentRequest


@pytest.mark.anyio
async def test_screen_design_agent_returns_not_implemented() -> None:
    agent = ScreenDesignAgent()

    response = await agent.generate(AgentRequest(project_id="PRJ-001"))

    assert response.success is False
    assert response.agent_name == "ScreenDesignAgent"
    assert response.error == "Screen design generation agent is not implemented yet"
