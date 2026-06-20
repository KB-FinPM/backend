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

    if case["name"] == "blocked_status_alias":
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

    if case["name"] == "stopword_not_assignee":
        todos = response.result.get("todos") or []
        for todo in todos:
            assert todo.get("assignee") not in case["expected_forbidden_assignee_values"]
        return

    assert response.success is True
    todo = response.result["todos"][0]
    assert todo["due_date"] == case["expected_due_date"]
    assert todo["assignee"] == case["expected_assignee"]
