# EN: Core agent adapter for generating screen design artifacts.
# KO: 화면설계서 산출물 생성을 위한 Core Agent adapter입니다.

from app.core.logger import get_logger
from app.schemas.agent import AgentRequest, AgentResponse

logger = get_logger(__name__)


class ScreenDesignAgent:
    """Adapter slot for the future screen design generation agent implementation."""

    AGENT_NAME = "ScreenDesignAgent"

    async def generate(self, request: AgentRequest) -> AgentResponse:
        logger.info(
            f"[{self.AGENT_NAME}] generate requested | "
            f"project_id={request.project_id}"
        )

        # TODO: Replace this placeholder with the screen design agent source.
        return AgentResponse(
            success=False,
            agent_name=self.AGENT_NAME,
            error="Screen design generation agent is not implemented yet",
        )


screen_design_agent = ScreenDesignAgent()
