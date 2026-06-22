# EN: Tests for user input normalization orchestration.
# KO: 사용자 입력 표준화 Orchestrator 테스트입니다.

import pytest

from app.orchestrator.input_orchestrator import InputOrchestrator
from app.schemas.io_agent import (
    InputAgentRequest,
    InputFilePayload,
    InputType,
    NormalizedRequestType,
)


@pytest.mark.anyio
async def test_input_orchestrator_routes_file_input_to_document_parser() -> None:
    orchestrator = InputOrchestrator()

    response = await orchestrator.normalize(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.FILE,
            files=[
                InputFilePayload(
                    file_name="requirements.txt",
                    file_bytes=b"requirements",
                )
            ],
        )
    )

    assert response.success is True
    assert response.structured_context["text"] == "requirements"


@pytest.mark.anyio
async def test_input_orchestrator_routes_text_input_to_chat_agent() -> None:
    orchestrator = InputOrchestrator()

    response = await orchestrator.normalize(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "이 요구사항으로 WBS 만들어줘"},
            context={"selected_document_ids": ["DOC-REQ-001"]},
        )
    )

    assert response.success is True
    assert response.normalized_request_type == NormalizedRequestType.CHAT_MESSAGE
    assert response.structured_context["intent"] == "GENERATE_ARTIFACT"
    assert response.structured_context["target_artifact_type"] == "WBS"
    assert response.structured_context["source_document_ids"] == ["DOC-REQ-001"]


@pytest.mark.anyio
async def test_input_orchestrator_normalizes_artifact_request() -> None:
    orchestrator = InputOrchestrator()

    response = await orchestrator.normalize(
        InputAgentRequest(
            project_id="PRJ-001",
            permission_scope=["project:PRJ-001:write"],
            input_type=InputType.ARTIFACT_REQUEST,
            raw_payload={"target_artifact_type": "REQUIREMENT_SPEC"},
            context={"source_document_ids": ["DOC-001"]},
        )
    )

    assert response.success is True
    assert response.normalized_request_type == NormalizedRequestType.ARTIFACT_GENERATION
    assert response.structured_context["raw_payload"] == {
        "target_artifact_type": "REQUIREMENT_SPEC"
    }
    assert response.structured_context["context"] == {
        "source_document_ids": ["DOC-001"]
    }
    assert response.structured_context["permission_scope"] == ["project:PRJ-001:write"]


@pytest.mark.anyio
async def test_input_orchestrator_normalizes_meeting_notes() -> None:
    orchestrator = InputOrchestrator()

    response = await orchestrator.normalize(
        InputAgentRequest(
            project_id="PRJ-001",
            permission_scope=["project:read"],
            input_type=InputType.MEETING_NOTES,
            raw_payload={
                "meeting_notes": "회의일시: 2025. 1.16(목)\n법제처 자료를 RPA를 통해 축적 가능여부 검토예정 (임태운 감사역)"
            },
            context={"source_document_ids": ["DOC-001"]},
        )
    )

    assert response.success is True
    assert response.normalized_request_type == (
        NormalizedRequestType.SCHEDULE_TODO_EXTRACTION
    )
    assert "법제처 자료" in response.structured_context["meeting_notes"]
    assert response.structured_context["context"] == {
        "source_document_ids": ["DOC-001"]
    }
    extraction = response.structured_context["meeting_todo_extraction"]
    assert extraction["todo_items"][0]["assignee"] == "임태운 감사역"
    assert extraction["todo_items"][0]["source_sentence"]
