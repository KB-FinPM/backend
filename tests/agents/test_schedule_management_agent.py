# EN: Tests for schedule management MVP todo extraction.
# KO: 일정관리 Agent MVP todo 추출 동작 테스트입니다.

import pytest

from app.agents.core_agents.schedule_management_agent.agent import (
    ScheduleManagementAgent,
)
from app.schemas.agent import AgentRequest
from app.schemas.schedule import ScheduleTodoList


@pytest.mark.anyio
async def test_schedule_management_agent_extracts_todos_from_meeting_notes() -> None:
    agent = ScheduleManagementAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            documents=[
                {
                    "chunk_id": "CHUNK-001",
                    "document_id": "DOC-MEETING-001",
                    "text": "meeting notes",
                }
            ],
            context={
                "meeting_notes": (
                    "김민수는 로그인 범위 검토를 2026-06-10까지 진행한다. "
                    "이영희는 API 예외 정책을 정리한다."
                ),
                "source_document_ids": ["DOC-MEETING-001"],
            },
        )
    )

    assert response.success is True
    assert response.agent_name == "ScheduleManagementAgent"
    todo_list = ScheduleTodoList.model_validate(response.result)
    assert todo_list.artifact_type == "SCHEDULE_TODO_LIST"
    assert len(todo_list.todos) == 2
    assert todo_list.todos[0].todo_id == "TODO-001"
    assert todo_list.todos[0].title == "로그인 범위 검토"
    assert todo_list.todos[0].assignee == "김민수"
    assert todo_list.todos[0].due_date == "2026-06-10"
    assert todo_list.todos[0].source_document_id == "DOC-MEETING-001"
    assert todo_list.todos[0].source_chunk_ids == ["CHUNK-001"]


@pytest.mark.anyio
async def test_schedule_management_agent_rejects_missing_meeting_notes() -> None:
    agent = ScheduleManagementAgent()

    response = await agent.generate(
        AgentRequest(project_id="PRJ-001", context={"meeting_notes": "   "})
    )

    assert response.success is False
    assert response.agent_name == "ScheduleManagementAgent"
    assert response.error == "meeting_notes is required"


@pytest.mark.anyio
async def test_schedule_management_agent_does_not_invent_assignee_or_due_date() -> None:
    agent = ScheduleManagementAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "meeting_notes": (
                    "회의록: 로그인 범위 검토 필요. API 예외 정책 정리 필요."
                ),
                "source_document_ids": ["DOC-MEETING-001"],
            },
        )
    )

    assert response.success is True
    todo_list = ScheduleTodoList.model_validate(response.result)
    assert todo_list.todos[0].assignee is None
    assert todo_list.todos[0].due_date is None
    assert todo_list.todos[1].assignee is None
    assert todo_list.todos[1].due_date is None


@pytest.mark.anyio
async def test_schedule_management_agent_keeps_relative_due_date_unparsed() -> None:
    agent = ScheduleManagementAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "meeting_notes": "박지은은 배포 체크리스트를 이번 주 금요일까지 공유한다.",
            },
        )
    )

    assert response.success is True
    todo_list = ScheduleTodoList.model_validate(response.result)
    assert todo_list.todos[0].assignee == "박지은"
    assert todo_list.todos[0].due_date is None
    assert todo_list.todos[0].metadata["unparsed_due_date_text"] == "이번 주 금요일"


@pytest.mark.anyio
async def test_schedule_management_agent_returns_failure_when_no_todos_found() -> None:
    agent = ScheduleManagementAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={"meeting_notes": "오늘 회의에서는 프로젝트 현황을 공유했습니다."},
        )
    )

    assert response.success is False
    assert response.agent_name == "ScheduleManagementAgent"
    assert response.error == "No action items were found in meeting notes"


@pytest.mark.anyio
async def test_schedule_management_agent_extracts_korean_meeting_todo_fields() -> None:
    agent = ScheduleManagementAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "meeting_notes": (
                    "이병희는 요구사항 명세서 초안 작성 6월 14일까지 작성. "
                    "화면설계서 검토 필요. "
                    "이규정은 WBS 기준 일정 재정리를 다음 회의 전까지 하기로 함."
                ),
            },
        )
    )

    assert response.success is True
    todo_list = ScheduleTodoList.model_validate(response.result)
    assert len(todo_list.todos) == 3
    assert todo_list.todos[0].assignee == "이병희"
    assert todo_list.todos[0].due_date == "6월 14일"
    assert todo_list.todos[0].related_document == "요구사항명세서"
    assert todo_list.todos[1].status == "NEEDS_CONFIRMATION"
    assert todo_list.todos[1].related_document == "화면설계서"
    assert todo_list.todos[2].assignee == "이규정"
    assert todo_list.todos[2].due_date == "다음 회의 전"
    assert todo_list.todos[2].related_document == "WBS"
