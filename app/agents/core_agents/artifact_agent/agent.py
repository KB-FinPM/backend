# EN: Unified Core Agent adapter for PM artifact generation.
# KO: PM 산출물 생성을 통합 담당하는 Core Agent adapter입니다.

from app.agents.core_agents.requirement_agent.agent import (
    RequirementAgent,
    requirement_agent,
)
from app.agents.core_agents.screen_design_agent.agent import (
    ScreenDesignAgent,
    screen_design_agent,
)
from app.agents.core_agents.wbs_agent.agent import WbsAgent, wbs_agent
from app.core.logger import get_logger
from app.schemas.agent import AgentRequest, AgentResponse
from app.schemas.artifact import ArtifactType

logger = get_logger(__name__)


class ArtifactAgent:
    """
    Unified adapter for document/artifact generation.

    The backend calls this single agent boundary. Internally it may delegate to
    specialized adapters, or it can later be replaced by one integrated source.
    """

    AGENT_NAME = "ArtifactAgent"

    def __init__(
        self,
        requirement_generator: RequirementAgent = requirement_agent,
        wbs_generator: WbsAgent = wbs_agent,
        screen_design_generator: ScreenDesignAgent = screen_design_agent,
    ) -> None:
        self.requirement_generator = requirement_generator
        self.wbs_generator = wbs_generator
        self.screen_design_generator = screen_design_generator

    async def generate(self, request: AgentRequest) -> AgentResponse:
        artifact_type = self._target_artifact_type(request)
        logger.info(
            f"[{self.AGENT_NAME}] dispatch | "
            f"project_id={request.project_id} | artifact_type={artifact_type}"
        )

        if artifact_type == ArtifactType.REQUIREMENT_SPEC:
            return await self.requirement_generator.generate(request)

        if artifact_type == ArtifactType.WBS:
            return await self.wbs_generator.generate(request)

        if artifact_type == ArtifactType.SCREEN_DESIGN:
            return await self.screen_design_generator.generate(request)

        return AgentResponse(
            success=False,
            agent_name=self.AGENT_NAME,
            error=f"{artifact_type.value} generation is not implemented yet",
        )

    def _target_artifact_type(self, request: AgentRequest) -> ArtifactType:
        context = request.context or {}
        raw_artifact_type = context.get("target_artifact_type")
        if raw_artifact_type is None:
            return ArtifactType.REQUIREMENT_SPEC

        return ArtifactType(raw_artifact_type)


artifact_agent = ArtifactAgent()
