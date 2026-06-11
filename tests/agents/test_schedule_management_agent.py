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
                "current_date": "2026-06-10",
            },
        )
    )

    assert response.success is True
    assert response.agent_name == "ScheduleManagementAgent"
    todo_list = ScheduleTodoList.model_validate(response.result)
    assert todo_list.artifact_type == "SCHEDULE_TODO_LIST"
    assert len(todo_list.todos) == 2
    assert todo_list.todos[0].todo_id == "TODO-TEMP-001"
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
                "current_date": "2026-06-10",
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
async def test_schedule_management_agent_parses_relative_due_date() -> None:
    agent = ScheduleManagementAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "meeting_notes": "박지은은 배포 체크리스트를 이번 주 금요일까지 공유한다.",
                "current_date": "2026-06-10",
            },
        )
    )

    assert response.success is True
    todo_list = ScheduleTodoList.model_validate(response.result)
    assert todo_list.todos[0].assignee == "박지은"
    assert todo_list.todos[0].due_date == "2026-06-12"


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
                "current_date": "2026-06-10",
            },
        )
    )

    assert response.success is True
    todo_list = ScheduleTodoList.model_validate(response.result)
    assert len(todo_list.todos) == 3
    assert todo_list.todos[0].assignee == "이병희"
    assert todo_list.todos[0].due_date == "2026-06-14"
    assert todo_list.todos[0].related_document == "요구사항 정의서"
    assert todo_list.todos[1].status == "NEEDS_CONFIRMATION"
    assert todo_list.todos[1].related_document == "화면설계서"
    assert todo_list.todos[2].assignee == "이규정"
    assert todo_list.todos[2].due_date is None
    assert todo_list.todos[2].related_document == "WBS"


@pytest.mark.anyio
async def test_schedule_management_agent_extracts_required_todo_shape() -> None:
    agent = ScheduleManagementAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "action": "EXTRACT_TODOS_FROM_MEETING",
                "meeting_notes": "김PM이 6월 14일까지 요구사항 정의서 초안을 검토하기로 했습니다.",
                "current_date": "2026-06-10",
            },
        )
    )

    assert response.success is True
    todo = response.result["todos"][0]
    assert todo["title"] == "요구사항 정의서 초안 검토"
    assert todo["assignee"] == "김PM"
    assert todo["due_date"] == "2026-06-14"
    assert todo["status"] == "TODO"


@pytest.mark.anyio
async def test_schedule_management_agent_calculates_current_week() -> None:
    agent = ScheduleManagementAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "action": "SHOW_CURRENT_WEEK",
                "current_date": "2026-06-10",
                "project": {"start_date": "2026-06-01"},
            },
        )
    )

    assert response.success is True
    assert response.result["week_context"]["current_week"] == 2
    assert response.result["week_context"]["week_start_date"] == "2026-06-08"
    assert response.result["week_context"]["week_end_date"] == "2026-06-14"


@pytest.mark.anyio
async def test_schedule_management_agent_requests_wbs_when_this_week_needs_wbs() -> None:
    agent = ScheduleManagementAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "action": "SHOW_THIS_WEEK_TODOS",
                "current_date": "2026-06-10",
                "project": {"start_date": "2026-06-01"},
                "normalized_input": {"needs_context": ["WBS", "TODO_LIST"]},
            },
        )
    )

    assert response.success is True
    assert response.result["status"] == "REQUIRED_INFO"
    assert response.result["missing_fields"] == ["wbs"]
    assert response.result["metadata"]["required_context"] == "WBS"


@pytest.mark.anyio
async def test_schedule_management_agent_includes_wbs_tasks_for_this_week() -> None:
    agent = ScheduleManagementAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "action": "SHOW_THIS_WEEK_TODOS",
                "current_date": "2026-06-10",
                "project": {"start_date": "2026-06-01"},
                "normalized_input": {"needs_context": ["WBS", "TODO_LIST"]},
                "wbs_tasks": [
                    {
                        "task_id": "WBS-001",
                        "title": "요구사항 정의서 초안 검토",
                        "assignee": "김PM",
                        "start_date": "2026-06-08",
                        "end_date": "2026-06-14",
                    }
                ],
            },
        )
    )

    assert response.success is True
    assert response.result["status"] == "SUCCESS"
    assert response.result["todos"][0]["todo_id"] == "WBS-001"
    assert response.result["todos"][0]["source_type"] == "WBS"


@pytest.mark.anyio
async def test_schedule_management_agent_matches_todo_completion() -> None:
    agent = ScheduleManagementAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "action": "COMPLETE_TODO",
                "target_text": "요구사항 검토 완료했어",
                "todos": [
                    {
                        "todo_id": "TODO-001",
                        "title": "요구사항 정의서 초안 검토",
                        "status": "TODO",
                    }
                ],
            },
        )
    )

    assert response.success is True
    assert response.result["status"] == "READY_TO_UPDATE"
    assert response.result["matched_todo"]["todo_id"] == "TODO-001"
    assert response.result["matched_todo"]["next_status"] == "DONE"


@pytest.mark.anyio
async def test_schedule_management_agent_returns_ambiguous_completion_candidates() -> None:
    agent = ScheduleManagementAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "action": "COMPLETE_TODO",
                "target_text": "요구사항 검토 완료했어",
                "todos": [
                    {
                        "todo_id": "TODO-001",
                        "title": "요구사항 정의서 초안 검토",
                        "status": "TODO",
                    },
                    {
                        "todo_id": "TODO-002",
                        "title": "요구사항 정의서 고객 검토",
                        "status": "TODO",
                    },
                ],
            },
        )
    )

    assert response.success is True
    assert response.result["status"] == "CLARIFICATION_REQUIRED"
    assert len(response.result["candidates"]) == 2


@pytest.mark.anyio
async def test_schedule_management_agent_uses_real_wbs_rows_for_week_briefing() -> None:
    agent = ScheduleManagementAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "action": "SHOW_THIS_WEEK_TODOS",
                "current_date": "2026-06-10",
                "normalized_input": {"needs_context": ["WBS", "TODO_LIST"]},
                "wbs_context": {
                    "source_document_name": "WBS (15).xlsx",
                    "rows": [
                        {
                            "row_number": 10,
                            "레벨": "2",
                            "ID": "1",
                            "WBS명": "프로젝트관리",
                            "시작예정일": "2026.01.05",
                            "종료예정일": "2026.07.05",
                            "작업자": "작업자",
                        },
                        {
                            "row_number": 70,
                            "레벨": "2",
                            "ID": "3.5",
                            "WBS명": "테스트",
                            "시작예정일": "2026.05.21",
                            "종료예정일": "2026.06.16",
                            "작업자": "작업자",
                        },
                        {
                            "row_number": 73,
                            "레벨": "4",
                            "ID": "3.5.1.1",
                            "WBS명": "통합테스트설계",
                            "시작예정일": "2026.05.21",
                            "종료예정일": "2026.06.16",
                            "작업자": "작업자",
                        },
                        {
                            "row_number": 74,
                            "레벨": "4",
                            "ID": "3.5.1.2",
                            "WBS명": "통합테스트실행및결과",
                            "시작예정일": "2026.05.21",
                            "종료예정일": "2026.06.16",
                            "작업자": "작업자",
                        },
                        {
                            "row_number": 80,
                            "레벨": "2",
                            "ID": "3.6",
                            "WBS명": "이행",
                            "시작예정일": "2026.06.17",
                            "종료예정일": "2026.06.22",
                            "작업자": "작업자",
                        },
                    ],
                },
            },
        )
    )

    assert response.success is True
    assert response.result["status"] == "SUCCESS"
    assert response.result["week_context"]["project_start_date"] == "2026-01-05"
    assert response.result["week_context"]["project_end_date"] == "2026-07-05"
    assert response.result["week_context"]["current_week"] == 23
    assert response.result["week_context"]["week_start_date"] == "2026-06-08"
    assert response.result["week_context"]["week_end_date"] == "2026-06-14"
    assert response.result["current_phase"]["title"] == "테스트"
    titles = [todo["title"] for todo in response.result["todos"]]
    assert "통합테스트설계" in titles
    assert "통합테스트실행및결과" in titles
    assert "프로젝트관리" not in titles
    assert "이행" not in titles
    assert response.result["todos"][0]["assignee"] is None
    assert response.result["todos"][0]["assignee_display"] == "확인 필요"
    assert response.result["todos"][0]["status"] == "PLANNED_OR_UNKNOWN"
    assert "상시 업무" in response.result["assistant_message"]


@pytest.mark.anyio
async def test_schedule_management_agent_keeps_duplicate_wbs_ids_by_row() -> None:
    agent = ScheduleManagementAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "action": "SHOW_THIS_WEEK_TODOS",
                "current_date": "2026-03-10",
                "project": {"start_date": "2026-01-05"},
                "normalized_input": {"needs_context": ["WBS", "TODO_LIST"]},
                "wbs_context": {
                    "rows": [
                        {
                            "row_number": 51,
                            "ID": "3.3.1.2",
                            "WBS명": "업무인스턴스및코드설계",
                            "시작예정일": "2026.03.07",
                            "종료예정일": "2026.04.10",
                        },
                        {
                            "row_number": 52,
                            "ID": "3.3.1.2",
                            "WBS명": "데이터클린징설계",
                            "시작예정일": "2026.03.07",
                            "종료예정일": "2026.04.10",
                        },
                    ],
                },
            },
        )
    )

    todo_ids = [todo["todo_id"] for todo in response.result["todos"]]
    assert len(todo_ids) == 2
    assert todo_ids[0] != todo_ids[1]
    assert {todo["title"] for todo in response.result["todos"]} == {
        "업무인스턴스및코드설계",
        "데이터클린징설계",
    }


@pytest.mark.anyio
async def test_schedule_management_agent_does_not_overdue_empty_wbs_status() -> None:
    agent = ScheduleManagementAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "action": "SHOW_OVERDUE_TODOS",
                "current_date": "2026-06-10",
                "wbs_context": {
                    "rows": [
                        {
                            "row_number": 1,
                            "ID": "3.1",
                            "WBS명": "계획상종료업무",
                            "시작예정일": "2026.05.01",
                            "종료예정일": "2026.06.01",
                            "작업상태": None,
                            "실제시작일": None,
                            "실제종료일": None,
                        },
                        {
                            "row_number": 2,
                            "ID": "3.2",
                            "WBS명": "진행중종료초과업무",
                            "시작예정일": "2026.05.01",
                            "종료예정일": "2026.06.01",
                            "작업상태": "진행중",
                        },
                    ],
                },
            },
        )
    )

    assert [todo["title"] for todo in response.result["todos"]] == [
        "진행중종료초과업무"
    ]
