# EN: Business service for lightweight schedule/todo management.

from typing import Any

from app.orchestrator.schedule_orchestrator import (
    ScheduleOrchestrator,
    schedule_orchestrator,
)
from app.schemas.request import ScheduleTodoRequest
from app.schemas.response import ScheduleTodoResponse


class ScheduleService:
    """Coordinates schedule-management use cases without exposing agents to routers."""

    def __init__(
        self,
        orchestrator: ScheduleOrchestrator = schedule_orchestrator,
    ) -> None:
        self.orchestrator = orchestrator

    async def extract_todos(
        self,
        request: ScheduleTodoRequest,
        *,
        structured_context: dict[str, Any] | None = None,
    ) -> ScheduleTodoResponse:
        return await self.orchestrator.extract_todos(
            request,
            structured_context=structured_context,
        )
