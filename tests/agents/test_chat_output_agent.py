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
    assert "WBS 문서가 생성되었습니다" in response.message
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
