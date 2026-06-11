# EN: Tests for requirement artifact generation agent.
# KO: 요구사항 산출물 생성 Agent 테스트입니다.

import pytest

from app.agents.core_agents.requirement_agent.agent import RequirementAgent
from app.schemas.agent import AgentRequest
from util.agent_generation_utils import (
    assign_requirement_ids,
    extract_requirement_atoms_from_pipe_tables,
)


@pytest.mark.anyio
async def test_requirement_agent_generates_structured_draft_from_chunks() -> None:
    agent = RequirementAgent()
    request = AgentRequest(
        project_id="PRJ-001",
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
    assert response.result["requirements"][0]["requirement_id"] == "REQ-00001"
    assert response.result["requirements"][0]["source_document_id"] == "DOC-001"
    assert response.result["requirements"][0]["source_chunk_ids"] == ["CHUNK-001"]


@pytest.mark.anyio
async def test_requirement_agent_uses_orchestrator_for_table_extraction() -> None:
    class StubOrchestrator:
        def __init__(self) -> None:
            self.table_called = False
            self.llm_called = False

        async def invoke_agent_llm(self, system_prompt: str, user_prompt: str, max_tokens: int = 4000) -> str:
            self.llm_called = True
            assert "표 기반 요구사항 후보" in user_prompt
            return (
                '[{"category":"기능","biz_requirement_name":"회원",'
                '"requirement_name":"회원 조회","requirement_type":"기능요구사항",'
                '"domain":"개발상세","feature":"회원 조회",'
                '"description":"회원 목록을 조회한다.","note":"",'
                '"source_document_id":"DOC-001","source_chunk_id":"CHUNK-001"}]'
            )

        def extract_requirement_atoms_from_pipe_tables(self, documents):
            self.table_called = True
            assert documents
            return assign_requirement_ids(
                extract_requirement_atoms_from_pipe_tables(documents)
            )

    orchestrator = StubOrchestrator()
    agent = RequirementAgent()
    request = AgentRequest(
        project_id="PRJ-001",
        documents=[
            {
                "chunk_id": "CHUNK-001",
                "document_id": "DOC-001",
                "section_title": "상세요건",
                "text": "개발상세\n회원 | 회원 조회 | 회원 목록을 조회한다.",
            }
        ],
        context={"generation_orchestrator": orchestrator},
    )

    response = await agent.generate(request)

    assert orchestrator.table_called is True
    assert orchestrator.llm_called is True
    assert response.success is True
    assert response.result["artifact_type"] == "REQUIREMENT_SPEC"
    assert response.result["requirements"][0]["requirement_id"] == "REQ-00001"
    assert response.result["requirements"][0]["source_document_id"] == "DOC-001"


@pytest.mark.anyio
async def test_requirement_agent_fails_without_source_chunks() -> None:
    agent = RequirementAgent()
    request = AgentRequest(project_id="PRJ-001", documents=[])

    response = await agent.generate(request)

    assert response.success is False
    assert response.error == (
        "No source document chunks available for requirement generation"
    )
