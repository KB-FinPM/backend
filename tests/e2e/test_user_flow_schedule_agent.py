from __future__ import annotations

import pytest

from app.schemas.chat import ChatMessageRequest

PROJECT_ID = "PRJ-TEST-001"
INTERNAL_FRAGMENTS = (
    "Input Agent",
    "Output Agent",
    "GenerationOrchestrator",
    "SCHEDULE_QUERY",
    "structured_context",
    "traceback",
)


def assert_user_facing_message(message: str) -> None:
    assert message.strip()
    lowered = message.lower()
    for fragment in INTERNAL_FRAGMENTS:
        assert fragment.lower() not in lowered


def scheduled_wbs_context() -> dict:
    return {
        "current_date": "2026-06-10",
        "project": {"start_date": "2026-06-01", "end_date": "2026-08-31"},
        "wbs_tasks": [
            {
                "task_id": "WBS-001",
                "title": "Requirement review",
                "planned_start_date": "2026-06-08",
                "planned_end_date": "2026-06-14",
                "assignee": "PM",
            },
            {
                "task_id": "WBS-002",
                "title": "Deployment preparation",
                "planned_start_date": "2026-06-15",
                "planned_end_date": "2026-06-21",
                "assignee": "DevOps",
            },
        ],
        "wbs_context": {
            "rows": [
                {
                    "row_number": 1,
                    "ID": "1",
                    "WBS명": "Project management",
                    "planned_start_date": "2026-06-01",
                    "planned_end_date": "2026-08-31",
                    "assignee": "PM",
                },
                {
                    "row_number": 2,
                    "ID": "1.1",
                    "WBS명": "Requirement review",
                    "planned_start_date": "2026-06-08",
                    "planned_end_date": "2026-06-14",
                    "assignee": "PM",
                },
                {
                    "row_number": 3,
                    "ID": "1.2",
                    "WBS명": "Deployment preparation",
                    "planned_start_date": "2026-06-15",
                    "planned_end_date": "2026-06-21",
                    "assignee": "DevOps",
                },
            ]
        },
    }


@pytest.mark.anyio
async def test_user_flow_asks_current_week_tasks_after_wbs_generation(
    scenario_services,
) -> None:
    orchestrator = scenario_services["chat_orchestrator"]

    response = await orchestrator.handle_message(
        ChatMessageRequest(
            project_id=PROJECT_ID,
            user_id="USER-001",
            message="이번 주 해야 할 일 알려줘",
            context=scheduled_wbs_context(),
        )
    )

    assert response.state == "COMPLETED"
    assert response.result["action"] == "SHOW_THIS_WEEK_TODOS"
    assert response.result["status"] == "SUCCESS"
    assert response.result["items"]
    assert any(
        todo["source_type"] == "WBS" and todo["title"] == "Requirement review"
        for todo in response.result["todos"]
    )
    assert any(
        item["title"] == "Requirement review"
        for item in response.result["items"]
    )
    assert_user_facing_message(response.message)


@pytest.mark.anyio
async def test_user_flow_asks_current_project_week_after_wbs_generation(
    scenario_services,
) -> None:
    orchestrator = scenario_services["chat_orchestrator"]

    response = await orchestrator.handle_message(
        ChatMessageRequest(
            project_id=PROJECT_ID,
            user_id="USER-001",
            message="현재 프로젝트 몇 주차야?",
            context=scheduled_wbs_context(),
        )
    )

    assert response.state == "COMPLETED"
    assert response.result["action"] == "SHOW_CURRENT_WEEK"
    assert response.result["week_context"]["current_week"] == 2
    assert response.result["week_context"]["week_start_date"] == "2026-06-08"
    assert response.result["week_context"]["week_end_date"] == "2026-06-14"
    assert_user_facing_message(response.message)


@pytest.mark.anyio
async def test_user_flow_schedule_agent_requests_wbs_when_schedule_context_missing(
    scenario_services,
) -> None:
    orchestrator = scenario_services["chat_orchestrator"]

    response = await orchestrator.handle_message(
        ChatMessageRequest(
            project_id=PROJECT_ID,
            user_id="USER-001",
            message="이번 주 해야 할 일 알려줘",
            context={
                "current_date": "2026-06-10",
                "project": {"start_date": "2026-06-01"},
            },
        )
    )

    assert response.state == "WAITING_REQUIRED_INFO"
    assert response.result["status"] == "REQUIRED_INFO"
    assert response.result["metadata"]["required_context"] == "WBS"
    assert response.result["upload_request"]["documentType"] == "WBS"
    assert_user_facing_message(response.message)


@pytest.mark.anyio
async def test_user_flow_marks_task_done_and_schedule_agent_reflects_status(
    scenario_services,
) -> None:
    orchestrator = scenario_services["chat_orchestrator"]
    repository = scenario_services["action_item_repository"]

    completion_response = await orchestrator.handle_message(
        ChatMessageRequest(
            project_id=PROJECT_ID,
            user_id="USER-001",
            message="TODO-001 done",
        )
    )
    todos_after_completion = await repository.list_project_todos(project_id=PROJECT_ID)

    assert completion_response.state == "COMPLETED"
    assert todos_after_completion[0]["status"] == "DONE"
    assert_user_facing_message(completion_response.message)

    query_response = await orchestrator.handle_message(
        ChatMessageRequest(
            project_id=PROJECT_ID,
            user_id="USER-001",
            message="이번 주 해야 할 일 알려줘",
            context=scheduled_wbs_context(),
        )
    )

    assert query_response.state == "COMPLETED"
    matching_items = [
        item for item in query_response.result["items"]
        if item["todo_id"] == "TODO-001"
    ]
    assert matching_items
    assert matching_items[0]["status"] == "DONE"
    assert_user_facing_message(query_response.message)


@pytest.mark.anyio
async def test_user_flow_missing_task_completion_is_user_facing(
    scenario_services,
) -> None:
    orchestrator = scenario_services["chat_orchestrator"]

    response = await orchestrator.handle_message(
        ChatMessageRequest(
            project_id=PROJECT_ID,
            user_id="USER-001",
            message="TODO-404 done",
        )
    )

    assert response.state == "FAILED"
    assert response.result["status"] == "NOT_FOUND"
    assert_user_facing_message(response.message)
