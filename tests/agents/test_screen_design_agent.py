# EN: Tests for screen design agent behavior.
# KO: 화면설계 Agent 동작 테스트입니다.

import pytest

from app.agents.core_agents.screen_design_agent.agent import ScreenDesignAgent
from app.schemas.agent import AgentRequest


def test_screen_design_agent_author_does_not_use_audit_fallbacks() -> None:
    agent = ScreenDesignAgent()

    assert (
        agent._author(
            {
                "author": "작성자",
                "writer": "local-dev-user",
                "created_by": "local-dev-user",
                "user_id": "local_dev_user",
            }
        )
        == ""
    )


def test_screen_design_agent_author_uses_explicit_author() -> None:
    agent = ScreenDesignAgent()

    assert agent._author({"author": "홍길동", "user_id": "local_dev_user"}) == "홍길동"


@pytest.mark.anyio
async def test_screen_design_agent_creates_one_screen_per_requirement_id() -> None:
    agent = ScreenDesignAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "author": "홍길동",
                "requirement_artifact": {
                    "requirements": [
                        {
                            "requirement_id": "REQ-0001",
                            "requirement_name": "회원 조회",
                            "description": "사용자는 회원 목록을 조회할 수 있어야 한다.",
                        },
                        {
                            "requirement_id": "REQ-0002",
                            "requirement_name": "권한 관리",
                            "description": "관리자는 사용자 권한을 변경할 수 있어야 한다.",
                        },
                    ]
                }
            },
        )
    )

    assert response.success is True
    assert response.agent_name == "ScreenDesignAgent"
    assert len(response.result["screens"]) == 2
    assert response.result["screens"][0]["source_requirement_ids"] == ["REQ-0001"]
    assert response.result["screens"][0]["description"] == "사용자는 회원 목록을 조회할 수 있어야 한다."
    assert response.result["screens"][0]["metadata"]["requirement_id"] == "REQ-0001"
    assert response.result["screens"][0]["metadata"]["description"] == "사용자는 회원 목록을 조회할 수 있어야 한다."
    assert response.result["metadata"]["author"] == "홍길동"
    assert response.result["screens"][0]["metadata"]["display_items"] == [
        {
            "item_name": "Description",
            "description": response.result["screens"][0]["metadata"]["display_items"][0]["description"],
        }
    ]
