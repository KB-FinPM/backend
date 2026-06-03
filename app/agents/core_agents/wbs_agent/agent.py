# EN: Core agent adapter for generating WBS artifacts.
# KO: WBS 산출물 생성을 위한 Core Agent adapter입니다.

from app.core.logger import get_logger
from app.schemas.agent import AgentRequest, AgentResponse

logger = get_logger(__name__)


class WbsAgent:
    """Adapter slot for the future WBS generation agent implementation."""

    AGENT_NAME = "WbsAgent"

    async def generate(self, request: AgentRequest) -> AgentResponse:
        logger.info(
            f"[{self.AGENT_NAME}] generate requested | "
            f"project_id={request.project_id}"
        )

        # TODO: Replace this placeholder with the WBS agent source when delivered.
        return AgentResponse(
            success=False,
            agent_name=self.AGENT_NAME,
            error="WBS generation agent is not implemented yet",
        )


wbs_agent = WbsAgent()
