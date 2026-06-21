# EN: Tests for requirement artifact generation agent.
# KO: 요구사항 산출물 생성 Agent 테스트입니다.

import json

import pytest

from app.agents.core_agents.requirement_agent.agent import RequirementAgent
from app.agents.core_agents.validator_agent.agent import ValidatorAgent
from app.schemas.agent import AgentRequest
from app.schemas.artifact import ArtifactType
from util.agent_generation_utils import (
    RequirementAtom,
    assign_requirement_ids,
    atoms_to_requirement_artifact,
)


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
    agent = RequirementAgent(
        model_invoker=orchestrator,
        requirement_atom_extractor=orchestrator.extract_requirement_atoms_from_pipe_tables,
    )
    request = AgentRequest(
        project_id="PRJ-001",
        documents=[{"chunk_id": "CHUNK-001", "document_id": "DOC-001", "text": "dummy"}],
    )

    response = await agent.generate(request)

    assert response.success is True
    assert len(orchestrator.calls) == 2
    assert response.result["artifact_type"] == "REQUIREMENT_SPEC"
    assert len(response.result["requirements"]) == 5


@pytest.mark.anyio
async def test_requirement_agent_includes_meeting_note_context() -> None:
    orchestrator = CapturingRequirementOrchestrator([])
    agent = RequirementAgent(
        model_invoker=orchestrator,
        requirement_atom_extractor=orchestrator.extract_requirement_atoms_from_pipe_tables,
    )
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
    )

    response = await agent.generate(request)

    assert response.success is True
    assert request.context is not None
    source_context = request.context.get("source_document_context")
    assert source_context is not None
    assert source_context["meeting_note_titles"] == ["2026-06-01 주간회의록.docx"]
    assert source_context["meeting_notes"][0]["document_type"] == "MEETING_NOTES"


def test_requirement_artifact_fills_empty_descriptions() -> None:
    artifact = atoms_to_requirement_artifact(
        [
            RequirementAtom(
                requirement_id="REQ-001",
                title="회원 목록 조회",
                requirement_name="회원 목록 조회",
                description="",
            )
        ],
        project_id="PRJ-001",
        generated_by="RequirementAgent",
    )

    assert artifact["requirements"][0]["description"] == "회원 목록 조회"


def test_requirement_artifact_prefers_title_for_empty_descriptions() -> None:
    artifact = atoms_to_requirement_artifact(
        [
            RequirementAtom(
                requirement_id="REQ-001",
                title="타이틀 우선",
                requirement_name="요구사항명 대체",
                description="",
                feature="기능 대체",
            )
        ],
        project_id="PRJ-001",
        generated_by="RequirementAgent",
    )

    assert artifact["requirements"][0]["description"] == "타이틀 우선"


def test_requirement_agent_table_fallback_fills_empty_descriptions() -> None:
    agent = RequirementAgent()
    payload = agent._table_atom_fallback_payload(
        RequirementAtom(
            requirement_id="REQ-001",
            title="",
            requirement_name="회원 목록 조회",
            description=" ",
            feature="회원 관리",
        )
    )

    assert payload["title"] == "회원 목록 조회"
    assert payload["description"] == "회원 목록 조회"


def test_requirement_agent_table_fallback_prefers_title_for_description() -> None:
    agent = RequirementAgent()
    payload = agent._table_atom_fallback_payload(
        RequirementAtom(
            requirement_id="REQ-001",
            title="타이틀 우선",
            requirement_name="요구사항명 대체",
            description="",
            feature="기능 대체",
        )
    )

    assert payload["description"] == "타이틀 우선"


def test_requirement_agent_table_fallback_does_not_promote_title_to_id() -> None:
    agent = RequirementAgent()
    payload = agent._table_atom_fallback_payload(
        RequirementAtom(
            requirement_id="KB통합품질관리시스템(IQMS)",
            title="KB통합품질관리시스템(IQMS)",
            requirement_name="KB통합품질관리시스템(IQMS)",
            description="시스템 요구사항을 확인한다.",
        )
    )

    assert payload["requirement_id"] == ""
    assert payload["title"] == "KB통합품질관리시스템(IQMS)"
    assert payload["source_requirement_id_raw"] == "KB통합품질관리시스템(IQMS)"


def test_assign_requirement_ids_replaces_non_identifier_duplicates() -> None:
    atoms = assign_requirement_ids(
        [
            RequirementAtom(
                requirement_id="프론트엔드 구현",
                title="프론트엔드 구현",
                requirement_name="프론트엔드 구현",
                description="프론트엔드 화면을 구현한다.",
                metadata={
                    "source": "구축요건정의서",
                    "raw_table_category": "서비스",
                },
            ),
            RequirementAtom(
                requirement_id="프론트엔드 구현",
                title="프론트엔드 구현",
                requirement_name="프론트엔드 구현",
                description="프론트엔드 상태 관리를 구현한다.",
                metadata={
                    "source": "구축요건정의서",
                    "raw_table_category": "서비스",
                },
            ),
        ]
    )

    requirement_ids = [atom.requirement_id for atom in atoms]
    assert requirement_ids == ["BSR-00001", "BSR-00002"]
    assert len(requirement_ids) == len(set(requirement_ids))
    assert atoms[0].metadata["source_requirement_id_raw"] == "프론트엔드 구현"
    assert atoms[1].metadata["source_requirement_id_raw"] == "프론트엔드 구현"


@pytest.mark.anyio
async def test_validator_accepts_fallback_artifact_after_id_assignment() -> None:
    atoms = assign_requirement_ids(
        [
            RequirementAtom(
                requirement_id="업무서비스 IQ+ CI/CD 배포 방식 변경",
                title="업무서비스 IQ+ CI/CD 배포 방식 변경",
                requirement_name="업무서비스 IQ+ CI/CD 배포 방식 변경",
                description="CI/CD 배포 방식을 변경한다.",
                metadata={
                    "source": "구축요건정의서",
                    "raw_table_category": "서비스",
                },
            ),
            RequirementAtom(
                requirement_id="업무서비스 IQ+ CI/CD 배포 방식 변경",
                title="업무서비스 IQ+ CI/CD 배포 방식 변경",
                requirement_name="업무서비스 IQ+ CI/CD 배포 방식 변경",
                description="변경된 배포 절차를 검증한다.",
                metadata={
                    "source": "구축요건정의서",
                    "raw_table_category": "서비스",
                },
            ),
        ]
    )
    artifact = atoms_to_requirement_artifact(
        atoms,
        project_id="pmpm",
        generated_by="RequirementAgent",
    )

    response = await ValidatorAgent().validate(
        artifact,
        expected_artifact_type=ArtifactType.REQUIREMENT_SPEC,
    )

    assert response.success is True
