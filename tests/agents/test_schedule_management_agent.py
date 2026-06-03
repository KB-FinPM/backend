# EN: Tests for schedule management agent adapter placeholder behavior.
# KO: 일정관리 Agent adapter placeholder 동작 테스트입니다.

import pytest

from app.agents.core_agents.schedule_management_agent.agent import (
    ScheduleManagementAgent,
)
from app.schemas.agent import AgentRequest


@pytest.mark.anyio
async def test_schedule_management_agent_returns_not_implemented() -> None:
    agent = ScheduleManagementAgent()

    response = await agent.generate(AgentRequest(project_id="PRJ-001"))

    assert response.success is False
    assert response.agent_name == "ScheduleManagementAgent"
    assert response.error == "Schedule management agent is not implemented yet"
