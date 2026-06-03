# EN: Tests for schedule service delegation behavior.

import pytest

from app.schemas.request import ScheduleTodoRequest
from app.schemas.response import ScheduleTodoResponse
from app.services.schedule_service import ScheduleService


class StubScheduleOrchestrator:
    def __init__(self) -> None:
        self.received_context: dict | None = None

    async def extract_todos(
        self,
        request: ScheduleTodoRequest,
        *,
        structured_context: dict | None = None,
    ) -> ScheduleTodoResponse:
        self.received_context = structured_context
        return ScheduleTodoResponse(
            project_id=request.project_id,
            result={"source": "stub-orchestrator"},
        )


@pytest.mark.anyio
async def test_schedule_service_delegates_to_orchestrator() -> None:
    orchestrator = StubScheduleOrchestrator()
    service = ScheduleService(orchestrator=orchestrator)

    response = await service.extract_todos(
        ScheduleTodoRequest(
            project_id="PRJ-001",
            meeting_notes="Discussed login scope.",
        ),
        structured_context={"normalized": True},
    )

    assert response.project_id == "PRJ-001"
    assert response.result == {"source": "stub-orchestrator"}
    assert orchestrator.received_context == {"normalized": True}
