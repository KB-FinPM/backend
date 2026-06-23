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


class CapturingRequirementOrchestrator(FakeRequirementOrchestrator):
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
        return await super().invoke_agent_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            call_index=call_index,
            call_total=call_total,
            call_label=call_label,
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


@pytest.mark.anyio
async def test_requirement_agent_includes_meeting_note_context() -> None:
    orchestrator = CapturingRequirementOrchestrator([])
    agent = RequirementAgent()
    request = AgentRequest(
        project_id="PRJ-001",
        documents=[
            {
                "chunk_id": "CHUNK-001",
                "document_id": "DOC-REQ-001",
                "text": "구축요건정의서 내용",
                "metadata": {
                    "document_type": "CONSTRUCTION_REQUIREMENT_DEFINITION",
                    "source_file_name": "구축요건정의서.v1.docx",
                },
            },
            {
                "chunk_id": "CHUNK-002",
                "document_id": "DOC-MEET-001",
                "text": "회의에서 추가된 화면 알림 요구사항",
                "metadata": {
                    "document_type": "MEETING_NOTES",
                    "source_file_name": "2026-06-01 주간회의록.docx",
                },
            },
        ],
        context={"generation_orchestrator": orchestrator},
    )

    response = await agent.generate(request)

    assert response.success is True
    assert request.context is not None
    source_context = request.context.get("source_document_context")
    assert source_context is not None
    assert source_context["meeting_note_titles"] == ["2026-06-01 주간회의록.docx"]
    assert source_context["meeting_notes"][0]["document_type"] == "MEETING_NOTES"


@pytest.mark.anyio
async def test_requirement_agent_splits_meeting_note_candidates_in_prompt() -> None:
    orchestrator = CapturingRequirementOrchestrator([])
    agent = RequirementAgent()
    request = AgentRequest(
        project_id="PRJ-001",
        documents=[
            {
                "chunk_id": "CHUNK-001",
                "document_id": "DOC-MEET-001",
                "text": (
                    "회의명 | 기술협상회의\n"
                    "회의 주제 | 업무 내용중 추가 필요한 부분 협의\n"
                    "1. 환율 고시 및 조회 | - 실시간 환율 채집 및 고시 관리 기능 필요 | - Pricing 기능 필요 | "
                    "- 채집 및 고시된 환율을 직원이 기간별로 조회할 수 있는 화면 구현\n"
                    "1-1. 실시간 환율 채집 및 고시 관리 기능 상세 | - 시장 LP 및 CMBS로부터의 시장 환율을 채집 및 고시 | "
                    "- 시장 채집 불가한 환율 및 Swap PT의 경우 수기 입력 기능 구현\n"
                ),
                "metadata": {
                    "document_type": "MEETING_NOTES",
                    "source_file_name": "시연용_회의록.v.1.docx",
                },
            }
        ],
        context={"generation_orchestrator": orchestrator},
    )

    response = await agent.generate(request)

    assert response.success is True
    assert orchestrator.calls
    prompt = orchestrator.calls[0]["user_prompt"]
    assert "실시간 환율 채집 및 고시 관리 기능 필요" in prompt
    assert "Pricing 기능 필요" in prompt
    assert "회의명" not in prompt
