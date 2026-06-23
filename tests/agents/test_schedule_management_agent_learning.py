import json
from pathlib import Path

import pytest

from app.agents.core_agents.schedule_management_agent.agent import ScheduleManagementAgent
from app.schemas.agent import AgentRequest


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "agent_accuracy_learning_seed_cases.json"
)


def _schedule_cases() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["schedule_agent_cases"]


@pytest.mark.anyio
@pytest.mark.parametrize("case", _schedule_cases(), ids=lambda case: case["name"])
async def test_schedule_management_agent_seed_cases(case: dict) -> None:
    agent = ScheduleManagementAgent()

    if case.get("action") == "UPDATE_TODO_STATUS" or case["name"] == "blocked_status_alias":
        response = await agent.generate(
            AgentRequest(
                project_id="PRJ-001",
                context={
                    "action": "UPDATE_TODO_STATUS",
                    "normalized_input": case["normalized_input"],
                    "todos": case["todos"],
                },
            )
        )
        assert response.success is True
        assert response.result["status"] == case["expected_status"]
        if case.get("expected_next_status"):
            assert response.result["matched_todo"]["next_status"] == case["expected_next_status"]
        return

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "action": "EXTRACT_TODOS_FROM_MEETING",
                "meeting_notes": case["meeting_notes"],
                "current_date": case.get("current_date", "2026-06-10"),
            },
        )
    )

    if case.get("expected_success") is False:
        assert response.success is False
        return

    assert response.success is True
    todos = response.result.get("todos") or []
    for todo in todos:
        for forbidden in case.get("expected_forbidden_assignee_values", []):
            assert todo.get("assignee") != forbidden

    if case.get("expected_count") is not None:
        assert len(todos) == case["expected_count"]
    if not todos:
        return

    todo = todos[0]
    if "expected_due_date" in case:
        assert todo["due_date"] == case["expected_due_date"]
    if "expected_assignee" in case:
        assert todo["assignee"] == case["expected_assignee"]
    if case.get("expected_status"):
        assert todo["status"] == case["expected_status"]
    if case.get("expected_title_contains"):
        assert case["expected_title_contains"] in todo["title"]
    for forbidden_title in case.get("expected_title_not_contains", []):
        assert forbidden_title not in todo["title"]
    if case.get("expected_unparsed_due"):
        assert todo["metadata"]["unparsed_due_date_text"] == case["expected_unparsed_due"]
