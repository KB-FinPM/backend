# EN: Tests for requirement artifact generation agent.
# KO: 요구사항 산출물 생성 Agent 테스트입니다.

import pytest

from app.agents.core_agents.requirement_agent.agent import RequirementAgent
from app.schemas.agent import AgentRequest
from util.agent_generation_utils import assign_requirement_ids, normalize_requirement_atoms


@pytest.mark.anyio
async def test_requirement_agent_generates_structured_draft_from_chunks() -> None:
    agent = RequirementAgent()
    request = AgentRequest(
        project_id="PRJ-001",
        context={"author": "홍길동"},
        documents=[
            {
                "chunk_id": "CHUNK-001",
                "document_id": "DOC-001",
                "text": "Login is required. Users must authenticate.",
            }
        ],
    )

    response = await agent.generate(request)

    assert response.success is True
    assert response.result["artifact_type"] == "REQUIREMENT_SPEC"
    assert response.result["requirements"][0]["requirement_id"] == "BSR-00001"
    assert response.result["requirements"][0]["source_document_id"] == "DOC-001"
    assert response.result["requirements"][0]["source_chunk_ids"] == ["CHUNK-001"]
    assert response.result["metadata"]["author"] == "홍길동"


@pytest.mark.anyio
async def test_requirement_agent_fails_without_source_chunks() -> None:
    agent = RequirementAgent()
    request = AgentRequest(project_id="PRJ-001", documents=[])

    response = await agent.generate(request)

    assert response.success is False
    assert response.error == (
        "No source document chunks available for requirement generation"
    )


def test_requirement_name_bullets_are_removed_from_normalized_atoms() -> None:
    atoms = assign_requirement_ids(
        normalize_requirement_atoms(
            [
                {
                    "requirement_id": "",
                    "requirement_name": "* 회원 조회",
                    "description": "- 회원 목록을 조회한다.",
                    "biz_requirement_name": "회원",
                }
            ]
        )
    )

    assert atoms[0].requirement_name == "회원 조회"
    assert atoms[0].title == "회원 조회"
    assert atoms[0].description == "- 회원 목록을 조회한다."
