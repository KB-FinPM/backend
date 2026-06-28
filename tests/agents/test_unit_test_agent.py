# EN: Tests for unit test case agent behavior.
# KO: 단위테스트케이스 Agent 동작 테스트입니다.

import pytest

from app.agents.core_agents.unit_test_agent.agent import UnitTestAgent
from app.agents.core_agents.validator_agent.agent import ValidatorAgent
from app.schemas.agent import AgentRequest


def test_unit_test_agent_author_does_not_use_audit_fallbacks() -> None:
    agent = UnitTestAgent()

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


def test_unit_test_agent_author_uses_explicit_writer() -> None:
    agent = UnitTestAgent()

    assert agent._author({"writer": "김PM", "user_id": "local_dev_user"}) == "김PM"


@pytest.mark.anyio
async def test_unit_test_agent_creates_one_case_per_screen_description() -> None:
    agent = UnitTestAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "project_name": "테스트 구축 프로젝트",
                "author": "김국민",
                "screen_artifact": {
                    "artifact_type": "SCREEN_DESIGN",
                    "screens": [
                        {
                            "screen_id": "SCR-001",
                            "name": "회원 조회",
                            "description": "회원 목록을 조회하고 상세를 확인한다.",
                            "source_requirement_ids": ["BSR-00001"],
                        },
                        {
                            "screen_id": "SCR-002",
                            "name": "회원 등록",
                            "description": "회원 정보를 등록하고 저장 결과를 확인한다.",
                            "source_requirement_ids": ["BSR-00002"],
                        },
                    ],
                },
            },
        )
    )

    assert response.success is True
    assert response.result["artifact_type"] == "UNITTEST_SPEC"
    assert response.result["metadata"]["project_name"] == "테스트 구축 프로젝트"
    assert response.result["metadata"]["author"] == "김국민"
    assert response.result["metadata"]["source_screen_count"] == 2
    assert [case["test_case_id"] for case in response.result["test_cases"]] == [
        "TEST-0001",
        "TEST-0002",
    ]
    assert response.result["test_cases"][0]["requirement_id"] == "BSR-00001"
    assert response.result["test_cases"][0]["requirement_name"] == "회원 조회"
    assert response.result["test_cases"][0]["scenario_id"] == "SCN-001"
    assert response.result["test_cases"][0]["test_case_name"] == "회원 조회 기본 검증"
    test_content_lines = response.result["test_cases"][0]["test_content"].splitlines()
    assert 3 <= len(test_content_lines) <= 6
    assert test_content_lines[0].startswith("1. ")
    assert any("조회 조건 입력" in line for line in test_content_lines)
    assert any("회원 목록을 조회하고 상세를 확인한다" in line for line in test_content_lines)
    assert not any("ㆍ" in line or "•" in line or "·" in line for line in test_content_lines)


@pytest.mark.anyio
async def test_unit_test_agent_reads_screen_artifact_from_documents() -> None:
    agent = UnitTestAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            documents=[
                {
                    "chunk_id": "CHUNK-001",
                    "document_id": "DOC-001",
                    "text": (
                        '{"artifact_type":"SCREEN_DESIGN","screens":['
                        '{"screen_id":"SCR-001","name":"회원 조회","description":"회원 목록을 조회한다.","source_requirement_ids":["BSR-00001"]}'
                        "]}"
                    ),
                }
            ],
        )
    )

    assert response.success is True
    assert len(response.result["test_cases"]) == 1
    assert response.result["test_cases"][0]["requirement_name"] == "회원 조회"
    assert response.result["test_cases"][0]["metadata"]["screen_id"] == "SCR-001"


@pytest.mark.anyio
async def test_unit_test_agent_reads_screen_artifact_from_chunk_metadata() -> None:
    agent = UnitTestAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            documents=[
                {
                    "chunk_id": "CHUNK-001",
                    "document_id": "DOC-001",
                    "chunk_index": 2,
                    "section_title": "회원 조회",
                    "text": "SCR-003 | 회원 조회 | 회원 목록을 조회한다. | 목록, 상세 | REQ-003",
                    "metadata": {
                        "screen_artifact": {
                            "artifact_type": "SCREEN_DESIGN",
                            "screens": [
                                {
                                    "screen_id": "SCR-003",
                                    "name": "회원 조회",
                                    "description": "회원 목록을 조회한다.",
                                    "source_requirement_ids": ["REQ-003"],
                                }
                            ],
                        }
                    },
                }
            ],
        )
    )

    assert response.success is True
    assert response.result["metadata"]["source_screen_count"] == 1
    assert response.result["test_cases"][0]["requirement_name"] == "회원 조회"
    assert response.result["test_cases"][0]["requirement_id"] == "REQ-003"


@pytest.mark.anyio
async def test_unit_test_agent_parses_screen_design_text_rows_from_documents() -> None:
    agent = UnitTestAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            documents=[
                {
                    "chunk_id": "CHUNK-001",
                    "document_id": "DOC-001",
                    "text": (
                        "# SCREEN_DESIGN\n"
                        "SCR-001 | 표지 | 표지 페이지 |  | \n"
                        "SCR-002 | 목차 | 목차 페이지 |  | \n"
                        "SCR-003 | 회원 조회 | 회원 목록을 조회한다. 회원 상세를 확인한다. | 항목A, 항목B | REQ-003\n"
                        "SCR-004 | 회원 등록 | 회원 정보를 등록하고 저장 결과를 확인한다. | 항목C, 항목D | REQ-004\n"
                    ),
                }
            ],
        )
    )

    assert response.success is True
    assert response.result["metadata"]["source_screen_count"] == 2
    assert [case["metadata"]["screen_id"] for case in response.result["test_cases"]] == [
        "SCR-003",
        "SCR-004",
    ]
    assert [case["requirement_id"] for case in response.result["test_cases"]] == [
        "REQ-003",
        "REQ-004",
    ]


@pytest.mark.anyio
async def test_unit_test_agent_falls_back_to_document_chunks_when_text_is_unstructured() -> None:
    agent = UnitTestAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            documents=[
                {
                    "chunk_id": "CHUNK-001",
                    "chunk_index": 0,
                    "text": "표지",
                },
                {
                    "chunk_id": "CHUNK-002",
                    "chunk_index": 1,
                    "text": "목차",
                },
                {
                    "chunk_id": "CHUNK-003",
                    "chunk_index": 2,
                    "section_title": "회원 조회",
                    "text": "회원 목록을 조회한다. 상세를 확인한다. REQ-101",
                },
                {
                    "chunk_id": "CHUNK-004",
                    "chunk_index": 3,
                    "section_title": "회원 등록",
                    "text": "회원 정보를 등록하고 저장 결과를 확인한다. REQ-102",
                },
            ],
        )
    )

    assert response.success is True
    assert response.result["metadata"]["source_screen_count"] == 2
    assert [case["metadata"]["screen_name"] for case in response.result["test_cases"]] == [
        "회원 조회",
        "회원 등록",
    ]
    assert [case["requirement_id"] for case in response.result["test_cases"]] == [
        "REQ-101",
        "REQ-102",
    ]


@pytest.mark.anyio
async def test_unit_test_agent_falls_back_to_screen_name_when_description_is_blank() -> None:
    agent = UnitTestAgent()
    validator = ValidatorAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "screen_artifact": {
                    "screens": [
                        {
                            "screen_id": "SCR-001",
                            "name": "대량거래 입력",
                            "description": "",
                            "source_requirement_ids": ["BSR-00001"],
                        }
                    ]
                }
            },
        )
    )
    validation = await validator.validate(response.result)

    assert response.success is True
    assert response.result["test_cases"][0]["test_content"].strip() != ""
    assert response.result["test_cases"][0]["metadata"]["screen_name"] == "대량거래 입력"
    assert response.result["test_cases"][0]["test_content"].splitlines()[0].startswith("1. ")
    assert validation.success is True


@pytest.mark.anyio
async def test_unit_test_agent_uses_save_template_for_registration_screen() -> None:
    agent = UnitTestAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "screen_artifact": {
                    "screens": [
                        {
                            "screen_id": "SCR-010",
                            "name": "회원 등록",
                            "description": "회원 정보를 등록하고 저장 결과를 확인한다.",
                            "source_requirement_ids": ["BSR-00010"],
                        }
                    ]
                }
            },
        )
    )

    assert response.success is True
    test_content_lines = response.result["test_cases"][0]["test_content"].splitlines()
    assert len(test_content_lines) <= 6
    assert any("회원 정보를 등록하고 저장 결과를 확인한다" in line for line in test_content_lines)
    assert any("저장 버튼 상태" in line for line in test_content_lines)
    assert any("정상 저장 후 결과 메시지" in line for line in test_content_lines)
    assert any("필수 입력 항목" in line for line in test_content_lines)
    assert not any("ㆍ" in line or "•" in line or "·" in line for line in test_content_lines)
    assert response.result["test_cases"][0]["test_case_name"] == "회원 등록 처리 검증"


@pytest.mark.anyio
async def test_unit_test_agent_skips_preliminary_pages_when_page_numbers_exist() -> None:
    agent = UnitTestAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "screen_artifact": {
                    "artifact_type": "SCREEN_DESIGN",
                    "screens": [
                        {
                            "screen_id": "SCR-001",
                            "name": "표지",
                            "description": "문서 표지",
                            "source_requirement_ids": ["REQ-001"],
                            "metadata": {"page_number": 1},
                        },
                        {
                            "screen_id": "SCR-002",
                            "name": "목차",
                            "description": "문서 목차",
                            "source_requirement_ids": ["REQ-002"],
                            "metadata": {"page_number": 2},
                        },
                        {
                            "screen_id": "SCR-003",
                            "name": "회원 조회",
                            "description": "ㆍ 회원 목록을 조회한다.\nㆍ 상세를 확인한다.",
                            "source_requirement_ids": ["REQ-003"],
                            "metadata": {"page_number": 3},
                        },
                    ],
                }
            },
        )
    )

    assert response.success is True
    assert len(response.result["test_cases"]) == 1
    assert response.result["test_cases"][0]["metadata"]["screen_id"] == "SCR-003"
    assert response.result["test_cases"][0]["requirement_id"] == "REQ-003"
