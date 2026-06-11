# EN: Tests for unit test case agent behavior.
# KO: 단위테스트케이스 Agent 동작 테스트입니다.

import pytest

from app.agents.core_agents.unit_test_agent.agent import UnitTestAgent
from app.agents.core_agents.validator_agent.agent import ValidatorAgent
from app.schemas.agent import AgentRequest


@pytest.mark.anyio
async def test_unit_test_agent_creates_cases_from_requirements() -> None:
    agent = UnitTestAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "project_name": "테스트 구축 프로젝트",
                "author": "김국민",
                "requirement_artifact": {
                    "requirements": [
                        {
                            "requirement_id": "REQ-00001",
                            "title": "회원 조회",
                            "description": "- 회원 목록을 조회한다.\\n- 회원 상세를 조회한다.",
                            "metadata": {
                                "requirement_name": "회원 조회",
                                "biz_requirement_id": "Biz-0001",
                            },
                        },
                        {
                            "requirement_id": "REQ-00002",
                            "title": "회원 등록",
                            "description": "회원 정보를 등록한다.",
                            "metadata": {
                                "requirement_name": "회원 등록",
                                "biz_requirement_id": "Biz-0001",
                            },
                        },
                        {
                            "requirement_id": "REQ-00003",
                            "title": "권한 변경",
                            "description": "권한을 변경한다.",
                            "metadata": {
                                "requirement_name": "권한 변경",
                                "biz_requirement_id": "Biz-0002",
                            },
                        },
                    ]
                },
            },
        )
    )

    assert response.success is True
    assert response.result["artifact_type"] == "UNITTEST_SPEC"
    assert response.result["metadata"]["project_name"] == "테스트 구축 프로젝트"
    assert response.result["metadata"]["author"] == "김국민"
    assert [case["test_case_id"] for case in response.result["test_cases"]] == [
        "TEST-0001-001",
        "TEST-0001-002",
        "TEST-0002-001",
    ]
    assert response.result["test_cases"][0]["requirement_id"] == "REQ-00001"
    assert response.result["test_cases"][0]["requirement_name"] == "회원 조회"
    assert response.result["test_cases"][0]["scenario_id"] == "Biz-0001"
    assert response.result["test_cases"][0]["test_case_name"] == "회원 조회 화면"
    assert response.result["test_cases"][0]["test_content"] == (
        "- 회원 목록을 조회한다.\n"
        "- 회원 상세를 조회한다."
    )


@pytest.mark.anyio
async def test_unit_test_agent_reads_requirement_metadata_from_documents() -> None:
    agent = UnitTestAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            documents=[
                {
                    "chunk_id": "CHUNK-001",
                    "document_id": "DOC-001",
                    "text": "회원 조회",
                    "metadata": {
                        "requirement": {
                            "requirement_id": "REQ-00001",
                            "title": "회원 조회",
                            "description": "회원 목록을 조회한다.",
                            "metadata": {
                                "requirement_name": "회원 조회",
                                "biz_requirement_id": "Biz-0001",
                            },
                        }
                    },
                }
            ],
        )
    )

    assert response.success is True
    assert response.result["test_cases"][0]["test_case_id"] == "TEST-0001-001"


@pytest.mark.anyio
async def test_unit_test_agent_preserves_blank_test_content_for_validation() -> None:
    agent = UnitTestAgent()
    validator = ValidatorAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "requirement_artifact": {
                    "requirements": [
                        {
                            "requirement_id": "REQ-00001",
                            "title": "대량거래 입력",
                            "description": "",
                            "metadata": {
                                "requirement_name": "대량거래 입력",
                                "biz_requirement_id": "Biz-0001",
                                "description": "",
                            },
                        }
                    ]
                }
            },
        )
    )
    validation = await validator.validate(response.result)

    assert response.success is True
    assert response.result["test_cases"][0]["test_content"] == " "
    assert response.result["test_cases"][0]["metadata"]["test_content"] == " "
    assert validation.success is True
