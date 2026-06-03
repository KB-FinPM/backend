# EN: Core agent adapter for lightweight schedule/todo management.
# KO: 회의록 기반 todo 중심 일정관리를 위한 Core Agent adapter입니다.

from app.core.logger import get_logger
from app.schemas.agent import AgentRequest, AgentResponse

logger = get_logger(__name__)


class ScheduleManagementAgent:
    """Adapter slot for future meeting-notes-to-todo schedule management."""

    AGENT_NAME = "ScheduleManagementAgent"

    async def generate(self, request: AgentRequest) -> AgentResponse:
        logger.info(
            f"[{self.AGENT_NAME}] generate requested | "
            f"project_id={request.project_id}"
        )

        # TODO: Replace this placeholder with meeting-notes-based todo extraction.
        return AgentResponse(
            success=False,
            agent_name=self.AGENT_NAME,
            error="Schedule management agent is not implemented yet",
        )


schedule_management_agent = ScheduleManagementAgent()
