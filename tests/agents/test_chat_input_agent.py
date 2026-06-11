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


@pytest.mark.anyio
async def test_chat_input_agent_detects_requirement_cleanup_generation_intent() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "구축요건정의서를 기준으로 요구사항 정리해줘"},
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "GENERATE_ARTIFACT"
    assert response.structured_context["target_artifact_type"] == "REQUIREMENT_SPEC"
    assert response.structured_context["source_document_ids"] == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "message",
    [
        "요구사항 명세서 생성해줘",
        "요구사항 정의서 만들어줘",
        "요구사항명세서 뽑아줘",
        "구축요건정의서를 기준으로 요구사항 정리해줘",
        "RFP 보고 요구사항 목록 뽑아줘",
    ],
)
async def test_chat_input_agent_requirement_generation_variants(
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
    assert response.structured_context["intent"] == "GENERATE_ARTIFACT"
    assert response.structured_context["action"] == "CREATE"
    assert response.structured_context["artifact_type"] == "REQUIREMENT_SPEC"
    assert response.structured_context["missing_slots"] == ["source_document_ids"]
    assert "normalized_query" in response.structured_context


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("message", "topic"),
    [
        ("요구사항 정의서가 뭐야?", "REQUIREMENT_SPEC"),
        ("구축요건정의서가 뭐야?", "CONSTRUCTION_REQUIREMENT_DEFINITION"),
        ("WBS가 뭐야?", "WBS"),
        ("화면설계서는 언제 만들어?", "SCREEN_DESIGN"),
        ("단위테스트케이스는 어떤 항목이 필요해?", "UNITTEST_SPEC"),
    ],
)
async def test_chat_input_agent_classifies_pm_concept_questions(
    message: str,
    topic: str,
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
    assert response.structured_context["action"] == "EXPLAIN"
    assert response.structured_context["topic"] == topic
    assert "target_artifact_type" not in response.structured_context


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("message", "intent", "schedule_action"),
    [
        ("회의록에서 할 일 뽑아줘", "EXTRACT_ACTION_ITEMS", "EXTRACT_TODOS_FROM_MEETING"),
        (
            "회의록: 김PM은 6월 14일까지 요구사항 정의서 초안을 검토하기로 했습니다.",
                "EXTRACT_ACTION_ITEMS",
                "EXTRACT_TODOS_FROM_MEETING",
            ),
        ("이번 주 해야 할 일 알려줘", "SCHEDULE_QUERY", "SHOW_THIS_WEEK_TODOS"),
        ("WBS 기준으로 이번 주 일정 알려줘", "SCHEDULE_QUERY", "SHOW_THIS_WEEK_TODOS"),
        ("다음 주에 뭐 해야 해?", "SCHEDULE_QUERY", "SHOW_NEXT_WEEK_TODOS"),
        ("오늘 챙길 일 알려줘", "SCHEDULE_QUERY", "SHOW_TODAY_TODOS"),
        ("김대리 할 일 뭐 남았어?", "SCHEDULE_QUERY", "SHOW_ASSIGNEE_TODOS"),
        (
            "지난 주 회의 TODO랑 이번 회의 내용 비교해줘",
            "SCHEDULE_QUERY",
            "COMPARE_WEEKLY_MEETING_TODOS",
        ),
        ("지금 프로젝트 몇 주차야?", "SCHEDULE_QUERY", "SHOW_CURRENT_WEEK"),
        ("기한 지난 업무 보여줘", "SCHEDULE_QUERY", "SHOW_OVERDUE_TODOS"),
        ("요구사항 검토 완료했어", "COMPLETE_TODO", "COMPLETE_TODO"),
    ],
)
async def test_chat_input_agent_classifies_schedule_requests(
    message: str,
    intent: str,
    schedule_action: str,
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
    assert response.structured_context["intent"] == intent
    assert response.structured_context["schedule_action"] == schedule_action
    assert response.structured_context["normalized_query"]
    if intent in {"SCHEDULE_QUERY", "EXTRACT_ACTION_ITEMS"}:
        assert response.structured_context["schedule_intent"] == "SCHEDULE_ASSISTANT"
        assert response.structured_context["needs_context"]


@pytest.mark.anyio
async def test_chat_input_agent_requests_meeting_notes_when_only_asked_to_extract() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "회의록 보고 TODO 정리해줘"},
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "EXTRACT_ACTION_ITEMS"
    assert response.structured_context["missing_slots"] == ["meeting_notes"]
