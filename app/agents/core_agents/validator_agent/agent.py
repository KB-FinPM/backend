from app.schemas.agent import AgentResponse
from app.core.logger import get_logger
from typing import Any

logger = get_logger(__name__)


class ValidatorAgent:
    """
    LLM 출력 검증 전담 Agent.
    역할: AgentResponse 결과의 스키마/규칙 검증
    """

    AGENT_NAME = "ValidatorAgent"

    async def validate(self, result: Any) -> AgentResponse:
        logger.info(f"[{self.AGENT_NAME}] validate start")

        # TODO: 스키마 검증 로직 구현
        # TODO: 필수 필드 존재 여부 확인
        # TODO: 규칙 기반 검증 (예: 요구사항 ID 형식 등)

        is_valid = True  # Mock

        if not is_valid:
            return AgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                error="검증 실패",
            )

        logger.info(f"[{self.AGENT_NAME}] validate passed")
        return AgentResponse(
            agent_name=self.AGENT_NAME,
            result=result,
        )


validator_agent = ValidatorAgent()
