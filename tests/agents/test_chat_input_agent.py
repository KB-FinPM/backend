# EN: Tests for natural chat input intent normalization.

import pytest

from app.agents.input_agents.chat_input_agent.agent import ChatInputAgent
from app.schemas.io_agent import InputAgentRequest, InputType


@pytest.mark.anyio
async def test_chat_input_agent_detects_requirement_generation_intent() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "요구사항 명세서 생성해줘"},
            context={"selected_document_ids": ["DOC-RFP-001"]},
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "GENERATE_ARTIFACT"
    assert response.structured_context["target_artifact_type"] == "REQUIREMENT_SPEC"
    assert response.structured_context["source_document_ids"] == ["DOC-RFP-001"]


@pytest.mark.anyio
async def test_chat_input_agent_detects_wbs_generation_intent() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "이 요구사항으로 WBS 만들어줘"},
            context={"selected_document_ids": ["DOC-REQ-001"]},
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "GENERATE_ARTIFACT"
    assert response.structured_context["target_artifact_type"] == "WBS"
    assert response.structured_context["source_document_ids"] == ["DOC-REQ-001"]


@pytest.mark.anyio
async def test_chat_input_agent_detects_wbs_synonym_generation_intent() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "일정표 작성해줘"},
            context={"selected_document_ids": ["DOC-REQ-001"]},
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "GENERATE_ARTIFACT"
    assert response.structured_context["target_artifact_type"] == "WBS"


@pytest.mark.anyio
async def test_chat_input_agent_detects_screen_design_generation_intent() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "화면설계서 작성해줘"},
            context={"selected_document_ids": ["DOC-REQ-001"]},
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "GENERATE_ARTIFACT"
    assert response.structured_context["target_artifact_type"] == "SCREEN_DESIGN"


@pytest.mark.anyio
async def test_chat_input_agent_detects_meeting_todo_intent() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "미팅 내용에서 액션아이템 정리해줘"},
            context={"selected_document_ids": ["DOC-MEETING-001"]},
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "EXTRACT_ACTION_ITEMS"
    assert response.structured_context["source_document_ids"] == ["DOC-MEETING-001"]
    assert response.structured_context["meeting_notes"] == (
        "미팅 내용에서 액션아이템 정리해줘"
    )


@pytest.mark.anyio
async def test_chat_input_agent_detects_meeting_action_cleanup_intent() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "회의록에서 해야 할 일 정리해줘"},
            context={"selected_document_ids": ["DOC-MEETING-001"]},
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "EXTRACT_ACTION_ITEMS"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "message",
    [
        "회의록 정리해줘",
        "회의내용 정리해줘",
    ],
)
async def test_chat_input_agent_does_not_treat_meeting_summary_as_todos(
    message: str,
) -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": message},
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "GENERAL_QA"
    assert response.structured_context["topic"] == "MEETING_NOTES"


@pytest.mark.anyio
async def test_chat_input_agent_handles_general_pm_question() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "RFP가 뭐야?"},
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "GENERAL_QA"
    assert response.structured_context["topic"] == "CONSTRUCTION_REQUIREMENT_DEFINITION"


@pytest.mark.anyio
async def test_chat_input_agent_does_not_misclassify_requirement_question() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "요구사항 정의서가 뭐야?"},
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "GENERAL_QA"
    assert "target_artifact_type" not in response.structured_context


@pytest.mark.anyio
async def test_chat_input_agent_rejects_empty_message() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "   "},
        )
    )

    assert response.success is False
    assert response.validation_errors == ["message is required"]


@pytest.mark.anyio
async def test_chat_input_agent_detects_confirmation_command() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "생성해"},
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "CONFIRM_PENDING_ACTION"
