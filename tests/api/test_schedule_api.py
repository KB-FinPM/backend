# EN: Tests for schedule-management API routing behavior.

from fastapi.testclient import TestClient

from app.dependencies import (
    get_input_orchestrator,
    get_output_orchestrator,
    get_schedule_service,
)
from app.schemas.io_agent import (
    InputAgentResponse,
    NormalizedRequestType,
    OutputAgentResponse,
)
from app.schemas.response import ScheduleTodoResponse


class StubScheduleService:
    def __init__(self) -> None:
        self.received_context: dict | None = None

    async def extract_todos(self, request, *, structured_context=None):
        self.received_context = structured_context
        return ScheduleTodoResponse(
            project_id=request.project_id,
            message="schedule todos extracted",
            result={
                "artifact_type": "SCHEDULE_TODO_LIST",
                "todos": [{"todo_id": "TODO-001", "title": "Confirm scope"}],
            },
        )


class StubInputOrchestrator:
    def __init__(self) -> None:
        self.received_input_type: str | None = None

    async def normalize(self, request):
        self.received_input_type = request.input_type
        return InputAgentResponse(
            agent_name="StubInputOrchestrator",
            normalized_request_type=NormalizedRequestType.SCHEDULE_TODO_EXTRACTION,
            structured_context={"normalized": True},
        )


class StubOutputOrchestrator:
    def __init__(self) -> None:
        self.received_response_type: str | None = None

    async def format(self, request):
        self.received_response_type = request.response_type
        return OutputAgentResponse(
            agent_name="StubOutputOrchestrator",
            display_payload={"formatted": True},
        )


def test_extract_schedule_todos_routes_through_io_orchestrators(
    client: TestClient,
) -> None:
    schedule_service = StubScheduleService()
    input_orchestrator = StubInputOrchestrator()
    output_orchestrator = StubOutputOrchestrator()
    client.app.dependency_overrides[get_schedule_service] = lambda: schedule_service
    client.app.dependency_overrides[get_input_orchestrator] = lambda: input_orchestrator
    client.app.dependency_overrides[get_output_orchestrator] = (
        lambda: output_orchestrator
    )

    try:
        response = client.post(
            "/schedule/todos",
            json={
                "project_id": "PRJ-001",
                "meeting_notes": "Discussed login scope.",
                "source_document_ids": ["DOC-001"],
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["project_id"] == "PRJ-001"
    assert body["result"]["todos"][0]["todo_id"] == "TODO-001"
    assert body["display"] == {"formatted": True}
    assert schedule_service.received_context == {"normalized": True}
    assert input_orchestrator.received_input_type == "MEETING_NOTES"
    assert output_orchestrator.received_response_type == "API_RESPONSE"
