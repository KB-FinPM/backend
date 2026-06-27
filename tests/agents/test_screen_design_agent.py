# EN: Tests for screen design agent behavior.
# KO: 화면설계 Agent 동작 테스트입니다.

import pytest

from app.agents.core_agents.screen_design_agent.agent import ScreenDesignAgent
from app.schemas.agent import AgentRequest


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
    description_lines = response.result["screens"][0]["description"].splitlines()
    assert 2 <= len(description_lines) <= 10
    assert not description_lines[0].startswith("ㆍ ")
    assert "사용자는 회원 목록을 조회할 수 있어야 한다." in description_lines[0]
    assert any("회원 조회 화면" in line for line in description_lines[1:])
    assert response.result["screens"][0]["metadata"]["requirement_id"] == "REQ-0001"
    assert response.result["screens"][0]["metadata"]["description"] == response.result["screens"][0]["description"]
    assert response.result["metadata"]["author"] == "홍길동"
    assert response.result["screens"][0]["metadata"]["display_items"] == [
        {
            "item_name": "Description",
            "description": response.result["screens"][0]["metadata"]["display_items"][0]["description"],
        }
    ]


def test_screen_design_description_renumbers_each_screen_from_one() -> None:
    agent = ScreenDesignAgent()

    description = agent._ensure_screen_description(
        "3. 환율 고시 및 조회 화면에서 조회 결과를 제공한다.\n4. 상세 확인 흐름을 제공한다.",
        "환율 고시 및 조회 화면",
    )

    description_lines = description.splitlines()
    assert "3. " not in description_lines[0]
    assert "4. " not in description_lines[1]
    assert "환율 고시 및 조회" in description_lines[0]


def test_screen_design_description_expands_for_richer_content() -> None:
    agent = ScreenDesignAgent()

    description = agent._ensure_screen_description(
        "조회 조건 입력, 결과 목록 표시, 상세 확인, 수정 저장, 삭제 처리, 파일 업로드, 승인 결과 반영, 통계 요약, 오류 메시지 안내",
        "종합 관리 화면",
    )

    description_lines = description.splitlines()
    assert 5 <= len(description_lines) <= 10
    assert all(not line.startswith("ㆍ ") for line in description_lines)
    assert any("조회 조건" in line for line in description_lines)
    assert any("저장" in line for line in description_lines)
    assert any("오류" in line for line in description_lines)
