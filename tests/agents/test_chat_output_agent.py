# EN: Tests for user-facing chat output rendering.

import pytest

from app.agents.output_agents.chat_agent.agent import ChatOutputAgent
from app.schemas.io_agent import OutputAgentRequest, OutputResponseType


INTERNAL_NAMES = {
    "GENERATE_ARTIFACT",
    "EXTRACT_ACTION_ITEMS",
    "GENERAL_QA",
    "CONFIRMATION_REQUIRED",
    "ACTION_COMPLETED",
    "SCHEDULE_TODO_LIST",
}


@pytest.mark.anyio
async def test_chat_output_agent_renders_artifact_completion() -> None:
    agent = ChatOutputAgent()

    response = await agent.render(
        OutputAgentRequest(
            project_id="PRJ-001",
            response_type=OutputResponseType.CHAT_RESPONSE,
            result_json={
                "event": "ACTION_COMPLETED",
                "result": {
                    "artifact": {
                        "artifact_id": "ART-001",
                        "artifact_type": "WBS",
                        "name": "WBS",
                    },
                    "exported_file": {
                        "file_name": "WBS.xlsx",
                        "storage_path": "s3://bucket/WBS.xlsx",
                    },
                },
            },
        )
    )

    assert response.success is True
    assert "WBS가 생성되었습니다" in response.message
    assert response.artifact_refs == [
        {"artifact_id": "ART-001", "artifact_type": "WBS", "name": "WBS"}
    ]
    assert not any(name in response.message for name in INTERNAL_NAMES)


@pytest.mark.anyio
async def test_chat_output_agent_renders_required_info_message() -> None:
    agent = ChatOutputAgent()

    response = await agent.render(
        OutputAgentRequest(
            project_id="PRJ-001",
            response_type=OutputResponseType.CHAT_RESPONSE,
            result_json={
                "event": "REQUIRED_INFO",
                "target_artifact_type": "REQUIREMENT_SPEC",
            },
        )
    )

    assert response.success is True
    assert "구축요건정의서 또는 RFP" in response.message
    assert response.display_payload["state"] == "WAITING_REQUIRED_INFO"
    assert not any(name in response.message for name in INTERNAL_NAMES)


@pytest.mark.anyio
async def test_chat_output_agent_renders_confirmation_request() -> None:
    agent = ChatOutputAgent()

    response = await agent.render(
        OutputAgentRequest(
            project_id="PRJ-001",
            response_type=OutputResponseType.CHAT_RESPONSE,
            result_json={
                "event": "CONFIRMATION_REQUIRED",
                "pending_action": {
                    "action_id": "ACT-001",
                    "action_type": "GENERATE_SCREEN_DESIGN",
                    "payload": {
                        "target_artifact_type": "SCREEN_DESIGN",
                        "source_document_ids": ["DOC-REQ-001"],
                    },
                },
            },
        )
    )

    assert response.success is True
    assert "화면설계서" in response.message
    assert response.display_payload["suggested_actions"][0]["label"] == "생성하기"
    assert not any(name in response.message for name in INTERNAL_NAMES)


@pytest.mark.anyio
async def test_chat_output_agent_renders_schedule_todo_result() -> None:
    agent = ChatOutputAgent()

    response = await agent.render(
        OutputAgentRequest(
            project_id="PRJ-001",
            response_type=OutputResponseType.CHAT_RESPONSE,
            result_json={
                "event": "ACTION_COMPLETED",
                "result": {
                    "artifact_type": "SCHEDULE_TODO_LIST",
                    "todos": [
                        {
                            "todo_id": "TODO-001",
                            "title": "로그인 범위 검토",
                            "description": "김민수는 로그인 범위 검토를 진행한다.",
                            "assignee": "김민수",
                            "due_date": None,
                        }
                    ],
                },
            },
        )
    )

    assert response.success is True
    assert "할 일 1건" in response.message
    assert response.display_payload["items"] == [
        {
            "todo_id": "TODO-001",
            "title": "로그인 범위 검토",
            "assignee": "김민수",
            "due_date": "미정",
            "description": "김민수는 로그인 범위 검토를 진행한다.",
        }
    ]
    assert not any(name in response.message for name in INTERNAL_NAMES)


@pytest.mark.anyio
async def test_chat_output_agent_masks_internal_errors() -> None:
    agent = ChatOutputAgent()

    response = await agent.render(
        OutputAgentRequest(
            project_id="PRJ-001",
            response_type=OutputResponseType.CHAT_RESPONSE,
            result_json={
                "event": "ACTION_FAILED",
                "error": "Schedule management agent is not implemented yet",
            },
        )
    )

    assert response.success is True
    assert "not implemented" not in response.message
    assert "다시 시도" in response.message
    assert response.display_payload["result"]["error"] == (
        "Schedule management agent is not implemented yet"
    )


@pytest.mark.anyio
async def test_chat_output_agent_rejects_unsupported_response_type() -> None:
    agent = ChatOutputAgent()

    response = await agent.render(
        OutputAgentRequest(
            project_id="PRJ-001",
            response_type=OutputResponseType.API_RESPONSE,
            result_json={"ok": True},
        )
    )

    assert response.success is False
    assert response.error == "unsupported response type"


@pytest.mark.anyio
async def test_chat_output_agent_explains_requirement_question_naturally() -> None:
    agent = ChatOutputAgent()

    response = await agent.render(
        OutputAgentRequest(
            project_id="PRJ-001",
            response_type=OutputResponseType.CHAT_RESPONSE,
            result_json={
                "event": "GENERAL_QA",
                "topic": "REQUIREMENT_SPEC",
                "query": "요구사항 정의서가 뭐야?",
            },
        )
    )

    assert response.success is True
    assert "요구사항 정의서는" in response.message
    assert "분류" not in response.message
    assert not any(name in response.message for name in INTERNAL_NAMES)


@pytest.mark.anyio
async def test_chat_output_agent_required_info_includes_upload_request() -> None:
    agent = ChatOutputAgent()

    response = await agent.render(
        OutputAgentRequest(
            project_id="PRJ-001",
            response_type=OutputResponseType.CHAT_RESPONSE,
            result_json={
                "event": "REQUIRED_INFO",
                "target_artifact_type": "REQUIREMENT_SPEC",
                "query": "요구사항 정리해줘",
            },
        )
    )

    upload_request = response.display_payload["result"]["upload_request"]
    assert upload_request["label"] == "구축요건 정의서 업로드"
    assert upload_request["required"] is True
    assert ".docx" in upload_request["acceptedTypes"]
    assert upload_request["documentType"] == "CONSTRUCTION_REQUIREMENT_DEFINITION"
    assert upload_request["originalMessage"] == "요구사항 정리해줘"


@pytest.mark.anyio
async def test_chat_output_agent_renders_current_week_result() -> None:
    agent = ChatOutputAgent()

    response = await agent.render(
        OutputAgentRequest(
            project_id="PRJ-001",
            response_type=OutputResponseType.CHAT_RESPONSE,
            result_json={
                "event": "SCHEDULE_RESULT",
                "result": {
                    "action": "SHOW_CURRENT_WEEK",
                    "status": "SUCCESS",
                    "week_context": {"current_week": 2},
                },
            },
        )
    )

    assert response.success is True
    assert response.message == "프로젝트 시작일 기준 현재는 2주차입니다."
    assert not any(name in response.message for name in INTERNAL_NAMES)


@pytest.mark.anyio
async def test_chat_output_agent_renders_schedule_table_metadata() -> None:
    agent = ChatOutputAgent()

    response = await agent.render(
        OutputAgentRequest(
            project_id="PRJ-001",
            response_type=OutputResponseType.CHAT_RESPONSE,
            result_json={
                "event": "SCHEDULE_RESULT",
                "result": {
                    "artifact_type": "SCHEDULE_TODO_LIST",
                    "action": "SHOW_THIS_WEEK_TODOS",
                    "status": "SUCCESS",
                    "todos": [
                        {
                            "todo_id": "TODO-001",
                            "title": "요구사항 정의서 초안 검토",
                            "assignee": "김PM",
                            "due_date": "2026-06-14",
                            "related_artifact": "요구사항 정의서",
                            "status": "TODO",
                        }
                    ],
                },
            },
        )
    )

    result = response.display_payload["result"]
    assert response.success is True
    assert "이번 주 진행해야 할 TODO는 1건" in response.message
    assert result["items"][0]["status"] == "TODO"
    assert result["schedule_table"]["columns"] == [
        "할 일",
        "담당자",
        "기한",
        "관련 산출물",
        "상태",
    ]


@pytest.mark.anyio
async def test_chat_output_agent_requests_wbs_for_schedule_required_info() -> None:
    agent = ChatOutputAgent()

    response = await agent.render(
        OutputAgentRequest(
            project_id="PRJ-001",
            response_type=OutputResponseType.CHAT_RESPONSE,
            result_json={
                "event": "SCHEDULE_RESULT",
                "result": {
                    "artifact_type": "SCHEDULE_TODO_LIST",
                    "action": "SHOW_THIS_WEEK_TODOS",
                    "status": "REQUIRED_INFO",
                    "missing_fields": ["wbs"],
                    "metadata": {"required_context": "WBS"},
                },
            },
        )
    )

    upload_request = response.display_payload["result"]["upload_request"]
    assert response.success is True
    assert "WBS를 업로드" in response.message
    assert upload_request["label"] == "WBS 업로드"
    assert upload_request["documentType"] == "WBS"
    assert upload_request["acceptedTypes"] == [".xlsx"]
    assert not any(name in response.message for name in INTERNAL_NAMES)


@pytest.mark.anyio
async def test_chat_output_agent_requests_meeting_notes_for_schedule_required_info() -> None:
    agent = ChatOutputAgent()

    response = await agent.render(
        OutputAgentRequest(
            project_id="PRJ-001",
            response_type=OutputResponseType.CHAT_RESPONSE,
            result_json={
                "event": "SCHEDULE_RESULT",
                "result": {
                    "artifact_type": "SCHEDULE_TODO_LIST",
                    "action": "EXTRACT_TODOS_FROM_MEETING",
                    "status": "REQUIRED_INFO",
                    "missing_fields": ["meeting_notes"],
                    "metadata": {"required_context": "MEETING_NOTES"},
                },
            },
        )
    )

    upload_request = response.display_payload["result"]["upload_request"]
    assert response.success is True
    assert "회의록 내용을 붙여넣거나" in response.message
    assert upload_request["label"] == "회의록 업로드"
    assert upload_request["documentType"] == "MEETING_NOTES"


@pytest.mark.anyio
async def test_chat_output_agent_renders_ambiguous_complete_todo() -> None:
    agent = ChatOutputAgent()

    response = await agent.render(
        OutputAgentRequest(
            project_id="PRJ-001",
            response_type=OutputResponseType.CHAT_RESPONSE,
            result_json={
                "event": "SCHEDULE_RESULT",
                "result": {
                    "action": "COMPLETE_TODO",
                    "status": "CLARIFICATION_REQUIRED",
                    "candidates": [
                        {"todo_id": "TODO-001", "title": "요구사항 정의서 초안 검토"},
                        {"todo_id": "TODO-002", "title": "요구사항 정의서 고객 검토"},
                    ],
                },
            },
        )
    )

    assert response.success is True
    assert "어떤 업무를 완료했는지 선택" in response.message
    assert response.display_payload["result"]["items"][0]["todo_id"] == "TODO-001"


@pytest.mark.anyio
async def test_chat_output_agent_no_pending_action_message_is_natural() -> None:
    agent = ChatOutputAgent()

    response = await agent.render(
        OutputAgentRequest(
            project_id="PRJ-001",
            response_type=OutputResponseType.CHAT_RESPONSE,
            result_json={"event": "NO_PENDING_ACTION", "action": "CANCEL"},
        )
    )

    assert response.success is True
    assert response.message == "현재 취소할 작업이 없습니다. 진행할 작업을 다시 입력해 주세요."
    assert "CANCEL_PENDING_ACTION" not in response.message
