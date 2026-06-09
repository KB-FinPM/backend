# EN: Business service for lightweight schedule/todo management.

from typing import Any

from app.orchestrator.schedule_orchestrator import (
    ScheduleOrchestrator,
    schedule_orchestrator,
)
from app.repositories.action_item_repository import ActionItemRepository
from app.schemas.request import ScheduleTodoRequest
from app.schemas.response import ScheduleTodoResponse


class ScheduleService:
    """Coordinates schedule-management use cases without exposing agents to routers."""

    def __init__(
        self,
        orchestrator: ScheduleOrchestrator = schedule_orchestrator,
        action_item_repository: ActionItemRepository | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.action_item_repository = action_item_repository

    async def extract_todos(
        self,
        request: ScheduleTodoRequest,
        *,
        structured_context: dict[str, Any] | None = None,
    ) -> ScheduleTodoResponse:
        response = await self.orchestrator.extract_todos(
            request,
            structured_context=structured_context,
        )
        if (
            response.success
            and self.action_item_repository is not None
            and isinstance(response.result, dict)
        ):
            todos = response.result.get("todos") or []
            if todos:
                saved_todos = await self.action_item_repository.save_extracted_todos(
                    project_id=request.project_id,
                    todos=todos,
                )
                response.result = {
                    **response.result,
                    "todos": saved_todos,
                    "metadata": {
                        **(response.result.get("metadata") or {}),
                        "saved": True,
                        "todo_count": len(saved_todos),
                    },
                }
        return response

    async def complete_todo(
        self,
        *,
        project_id: str,
        title_query: str,
    ) -> ScheduleTodoResponse:
        if self.action_item_repository is None:
            return ScheduleTodoResponse(
                success=False,
                project_id=project_id,
                message="todo storage is not available",
                result={},
            )

        completed_todo = await self.action_item_repository.complete_matching_todo(
            project_id=project_id,
            title_query=title_query,
        )
        if completed_todo is None:
            return ScheduleTodoResponse(
                success=False,
                project_id=project_id,
                message="matching todo not found",
                result={},
            )

        return ScheduleTodoResponse(
            project_id=project_id,
            message="todo completed",
            result={
                "artifact_type": "SCHEDULE_TODO_LIST",
                "todos": [completed_todo],
                "metadata": {"event": "TODO_COMPLETED"},
            },
        )
