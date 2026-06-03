# EN: Tests for schedule-management orchestration.

import pytest

from app.orchestrator.schedule_orchestrator import ScheduleOrchestrator
from app.schemas.agent import AgentResponse
from app.schemas.request import ScheduleTodoRequest


class StubScheduleAgent:
    def __init__(self, response: AgentResponse) -> None:
        self.response = response
        self.received_context: dict | None = None

    async def generate(self, request):
        self.received_context = request.context
        return self.response


@pytest.mark.anyio
async def test_schedule_orchestrator_extracts_valid_todos() -> None:
    agent = StubScheduleAgent(
        AgentResponse(
            agent_name="StubScheduleAgent",
            result={
                "artifact_type": "SCHEDULE_TODO_LIST",
                "todos": [
                    {
                        "todo_id": "TODO-001",
                        "title": "Confirm login scope",
                    }
                ],
            },
        )
    )
    orchestrator = ScheduleOrchestrator(schedule_agent=agent)

    response = await orchestrator.extract_todos(
        ScheduleTodoRequest(
            project_id="PRJ-001",
            meeting_notes="Discussed login scope.",
            source_document_ids=["DOC-001"],
        ),
        structured_context={"normalized": True},
    )

    assert response.success is True
    assert response.message == "schedule todos extracted"
    assert response.result["todos"][0]["todo_id"] == "TODO-001"
    assert agent.received_context["meeting_notes"] == "Discussed login scope."
    assert agent.received_context["normalized_input"] == {"normalized": True}


@pytest.mark.anyio
async def test_schedule_orchestrator_returns_agent_failure() -> None:
    orchestrator = ScheduleOrchestrator(
        schedule_agent=StubScheduleAgent(
            AgentResponse(
                success=False,
                agent_name="StubScheduleAgent",
                error="not ready",
            )
        )
    )

    response = await orchestrator.extract_todos(
        ScheduleTodoRequest(
            project_id="PRJ-001",
            meeting_notes="Discussed login scope.",
        )
    )

    assert response.success is False
    assert response.message == "not ready"
    assert response.result["agent_name"] == "StubScheduleAgent"
