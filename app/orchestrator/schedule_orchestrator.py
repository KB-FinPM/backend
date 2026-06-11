# EN: Orchestrates lightweight schedule/todo extraction flows.

from typing import Any

from app.agents.core_agents.schedule_management_agent.agent import (
    schedule_management_agent,
)
from app.agents.core_agents.validator_agent.agent import validator_agent
from app.core.logger import get_logger
from app.schemas.agent import AgentRequest, AgentResponse
from app.schemas.request import ScheduleTodoRequest
from app.schemas.response import ScheduleTodoResponse

logger = get_logger(__name__)


class ScheduleOrchestrator:
    """Coordinates meeting-notes-to-todo extraction through the schedule agent."""

    def __init__(
        self,
        schedule_agent: Any = schedule_management_agent,
        validator: Any = validator_agent,
    ) -> None:
        self.schedule_agent = schedule_agent
        self.validator = validator

    async def extract_todos(
        self,
        request: ScheduleTodoRequest,
        *,
        structured_context: dict[str, Any] | None = None,
    ) -> ScheduleTodoResponse:
        logger.info(
            "[ScheduleOrchestrator] extract_todos start | "
            f"project_id={request.project_id}"
        )
        agent_response = await self.schedule_agent.generate(
            AgentRequest(
                project_id=request.project_id,
                documents=[],
                context={
                    "action": "EXTRACT_TODOS_FROM_MEETING",
                    "meeting_notes": request.meeting_notes,
                    "source_document_ids": request.source_document_ids,
                    "permission_scope": request.permission_scope,
                    "normalized_input": structured_context or {},
                },
            )
        )
        if not agent_response.success:
            return self._failed_response(request, agent_response)

        validated_response = await self.validator.validate(agent_response.result)
        if not validated_response.success:
            return self._failed_response(request, validated_response)

        return ScheduleTodoResponse(
            project_id=request.project_id,
            message="schedule todos extracted",
            result=validated_response.result,
        )

    async def run_schedule_action(
        self,
        *,
        project_id: str,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> ScheduleTodoResponse:
        agent_response = await self.schedule_agent.generate(
            AgentRequest(
                project_id=project_id,
                documents=[],
                context={
                    **(context or {}),
                    "action": action,
                },
            )
        )
        if not agent_response.success:
            return ScheduleTodoResponse(
                success=False,
                message=agent_response.error or "schedule action failed",
                project_id=project_id,
                result={
                    "agent_name": agent_response.agent_name,
                    "error": agent_response.error,
                    "action": action,
                },
            )

        validated_response = await self.validator.validate(agent_response.result)
        if not validated_response.success:
            return ScheduleTodoResponse(
                success=False,
                message=validated_response.error or "schedule validation failed",
                project_id=project_id,
                result={
                    "agent_name": validated_response.agent_name,
                    "error": validated_response.error,
                    "action": action,
                },
            )

        return ScheduleTodoResponse(
            project_id=project_id,
            message="schedule action completed",
            result=validated_response.result,
        )

    def _failed_response(
        self,
        request: ScheduleTodoRequest,
        agent_response: AgentResponse,
    ) -> ScheduleTodoResponse:
        logger.warning(
            "[ScheduleOrchestrator] extract_todos failed | "
            f"project_id={request.project_id} | "
            f"agent={agent_response.agent_name} | error={agent_response.error}"
        )
        return ScheduleTodoResponse(
            success=False,
            message=agent_response.error or "schedule todo extraction failed",
            project_id=request.project_id,
            result={
                "agent_name": agent_response.agent_name,
                "error": agent_response.error,
            },
        )


schedule_orchestrator = ScheduleOrchestrator()
