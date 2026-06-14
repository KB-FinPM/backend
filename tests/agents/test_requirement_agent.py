# EN: Tests for requirement artifact generation agent.
# KO: 요구사항 산출물 생성 Agent 테스트입니다.

import json

import pytest

from app.agents.core_agents.requirement_agent.agent import RequirementAgent
from app.schemas.agent import AgentRequest
from util.agent_generation_utils import RequirementAtom


class FakeRequirementOrchestrator:
    def __init__(self, atoms: list[RequirementAtom]) -> None:
        self.atoms = atoms
        self.calls: list[dict[str, object]] = []

    def extract_requirement_atoms_from_pipe_tables(
        self,
        documents: list[dict],
    ) -> list[RequirementAtom]:
        return self.atoms

    async def invoke_agent_llm(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        call_index: int | None = None,
        call_total: int | None = None,
        call_label: str | None = None,
    ) -> str:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "call_index": call_index,
                "call_total": call_total,
                "call_label": call_label,
            }
        )
        if call_index == 1:
            payload = [
                {
                    "requirement_name": f"로그인 요청 처리 {item_index}",
                    "description": f"로그인 요청 {item_index}을 검증한다.",
                    "category": "기능",
                    "requirement_type": "기능요구사항",
                    "biz_requirement_id": "Biz-0001",
                    "biz_requirement_name": "인증",
                    "domain": "인증",
                    "feature": f"로그인 {item_index}",
                    "note": "보정",
                    "acceptance_criteria": [f"로그인 요청 {item_index}이 정상 처리된다."],
                }
                for item_index in range(1, 5)
            ]
        else:
            payload = [
                {
                    "requirement_name": "로그아웃 요청 처리 1",
                    "description": "로그아웃 요청 1을 검증한다.",
                    "category": "기능",
                    "requirement_type": "기능요구사항",
                    "biz_requirement_id": "Biz-0001",
                    "biz_requirement_name": "인증",
                    "domain": "인증",
                    "feature": "로그아웃 1",
                    "note": "보정",
                    "acceptance_criteria": ["로그아웃 요청 1이 정상 처리된다."],
                }
            ]
        return json.dumps(payload, ensure_ascii=False)


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
async def test_requirement_agent_fails_without_source_chunks() -> None:
    agent = RequirementAgent()
    request = AgentRequest(project_id="PRJ-001", documents=[])

    response = await agent.generate(request)

    assert response.success is False
    assert response.error == (
        "No source document chunks available for requirement generation"
    )


@pytest.mark.anyio
async def test_requirement_agent_batches_table_candidates() -> None:
    atoms = [
        RequirementAtom(
            requirement_id=f"REQ-{index:03d}",
            title=f"항목 {index}",
            requirement_name=f"항목 {index}",
            description=f"항목 {index} 설명",
            biz_requirement_id="Biz-0001",
            biz_requirement_name="업무",
            domain="업무",
            feature=f"기능 {index}",
        )
        for index in range(1, 6)
    ]
    orchestrator = FakeRequirementOrchestrator(atoms)
    agent = RequirementAgent()
    request = AgentRequest(
        project_id="PRJ-001",
        documents=[{"chunk_id": "CHUNK-001", "document_id": "DOC-001", "text": "dummy"}],
        context={"generation_orchestrator": orchestrator},
    )

    response = await agent.generate(request)

    assert response.success is True
    assert len(orchestrator.calls) == 2
    assert response.result["artifact_type"] == "REQUIREMENT_SPEC"
    assert len(response.result["requirements"]) == 5
