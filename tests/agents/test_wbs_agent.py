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
    assert response.error == "No requirement context available for WBS generation"


@pytest.mark.anyio
async def test_wbs_agent_uses_project_name_or_default_label(monkeypatch) -> None:
    monkeypatch.setattr(
        "util.agent_template_utils.settings.S3_STORAGE_BACKEND",
        "mock",
    )
    agent = WbsAgent()
    requirement_artifact = {
        "requirements": [
            {
                "requirement_id": "REQ-0001",
                "requirement_name": "회원 조회",
                "description": "사용자는 회원 목록을 조회할 수 있어야 한다.",
            }
        ]
    }

    named_response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "project_name": "차세대 FX 플랫폼",
                "requirement_artifact": requirement_artifact,
            },
        )
    )
    default_response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={"requirement_artifact": requirement_artifact},
        )
    )

    assert named_response.success is True
    assert named_response.result["metadata"]["project_name"] == "차세대 FX 플랫폼"
    assert named_response.result["tasks"][0]["name"] == "차세대 FX 플랫폼"
    assert default_response.success is True
    assert default_response.result["metadata"]["project_name"] == "프로젝트명"
    assert default_response.result["tasks"][0]["name"] == "프로젝트명"
