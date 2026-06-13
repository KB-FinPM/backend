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


def test_chat_input_agent_normalizes_typos_and_extracts_semantic_slots() -> None:
    agent = ChatInputAgent()

    normalized = agent.normalize_text("구축요건저의서로 요구사항명새서 뽀바줘")
    slots = agent.extract_semantic_slots(
        "구축요건저의서로 요구사항명새서 뽀바줘",
        {
            "uploaded_documents": [
                {
                    "document_id": "DOC-RFP-001",
                    "document_type": "CONSTRUCTION_REQUIREMENT_DEFINITION",
                    "file_name": "RFP.PDF",
                }
            ]
        },
    )

    assert "구축요건정의서" in normalized
    assert "요구사항명세서" in normalized
    assert "뽑아줘" in normalized
    assert slots["source_type"] == "CONSTRUCTION_REQUIREMENT_DEFINITION"
    assert slots["target_type"] == "REQUIREMENT_SPEC"
    assert slots["action"] == "GENERATE"
    assert slots["artifact_type"] == "REQUIREMENT_SPEC"
    assert slots["context_snapshot"]["uploaded_document_types"] == [
        "CONSTRUCTION_REQUIREMENT_DEFINITION"
    ]


def test_chat_input_agent_stays_semantic_parser_only() -> None:
    agent = ChatInputAgent()

    assert not any(
        hasattr(agent, attribute)
        for attribute in (
            "generation_agent",
            "generation_service",
            "schedule_agent",
            "schedule_service",
            "validator",
            "output_agent",
            "output_formatter",
        )
    )


def test_chat_input_agent_uses_last_agent_response_summary_as_context() -> None:
    agent = ChatInputAgent()

    slots = agent.extract_semantic_slots(
        "방금 말한 TODO 완료",
        {
            "last_agent_response_summary": {
                "action": "SHOW_THIS_WEEK_TODOS",
                "todo_count": 1,
            }
        },
    )

    assert slots["source_type"] == "LAST_AGENT_RESPONSE"
    assert slots["target_type"] == "TODO"
    assert slots["action"] == "COMPLETE"
    assert slots["context_snapshot"]["last_agent_response_summary"]["todo_count"] == 1


@pytest.mark.anyio
async def test_chat_input_agent_routes_meeting_todo_semantics_before_weekly_schedule() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "TODO 필요한데 이번주 회의록 기반으로 알려줘."},
            context={
                "uploaded_documents": [
                    {
                        "document_id": "DOC-MEETING-001",
                        "document_type": "MEETING_NOTES",
                        "file_name": "weekly-meeting.pdf",
                    }
                ]
            },
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "EXTRACT_ACTION_ITEMS"
    assert response.structured_context["schedule_action"] == "EXTRACT_TODOS_FROM_MEETING"
    assert response.structured_context["source_document_ids"] == ["DOC-MEETING-001"]
    assert response.structured_context["missing_slots"] == []
    assert response.structured_context["semantic_slots"]["source_type"] == "MEETING_NOTES"
    assert response.structured_context["semantic_slots"]["target_type"] == "TODO"
    assert response.structured_context["semantic_slots"]["time_range"] == "THIS_WEEK"


@pytest.mark.anyio
async def test_chat_input_agent_uses_generated_wbs_context_for_schedule_query() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "WBS 기준으로 할 일 알려줘"},
            context={
                "generated_artifacts": [
                    {
                        "artifact_id": "ART-WBS-001",
                        "artifact_type": "WBS",
                        "name": "프로젝트 WBS",
                    }
                ]
            },
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "SCHEDULE_QUERY"
    assert response.structured_context["schedule_action"] == "ASSISTANT_BRIEFING"
    assert response.structured_context["semantic_slots"]["source_type"] == "WBS"
    assert response.structured_context["semantic_slots"]["target_type"] == "TODO"
    assert response.structured_context["context_snapshot"]["generated_artifact_types"] == [
        "WBS"
    ]


@pytest.mark.anyio
async def test_chat_input_agent_matches_spacing_free_todo_completion() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "설계및테스트 완료"},
            context={
                "recent_todos": [
                    {
                        "todo_id": "TODO-001",
                        "title": "설계 및 테스트",
                        "status": "TODO",
                    }
                ]
            },
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "COMPLETE_TODO"
    assert response.structured_context["todo_title_query"] == "설계및테스트"
    assert response.structured_context["semantic_slots"]["action"] == "COMPLETE"
    assert response.structured_context["context_snapshot"]["recent_todo_count"] == 1


@pytest.mark.anyio
async def test_chat_input_agent_preserves_ambiguous_todo_completion_context() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "완료했어"},
            context={
                "recent_todos": [
                    {"todo_id": "TODO-001", "title": "요구사항 검토"},
                    {"todo_id": "TODO-002", "title": "화면설계서 작성"},
                ]
            },
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "COMPLETE_TODO"
    assert response.structured_context["todo_title_query"] == ""
    assert response.structured_context["context_snapshot"]["recent_todo_count"] == 2


@pytest.mark.anyio
async def test_chat_input_agent_asks_clarification_for_low_confidence_command() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "알려줘"},
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "CLARIFICATION_REQUIRED"
    assert response.structured_context["clarification_required"] is True
    assert response.structured_context["semantic_slots"]["clarification_required"] is True
