from typing import Any

from app.core.logger import get_logger
from app.schemas.agent import AgentResponse

logger = get_logger(__name__)


class ValidatorAgent:
    """Validates common agent output rules before post-processing or storage."""

    AGENT_NAME = "ValidatorAgent"

    async def validate(self, result: Any) -> AgentResponse:
        logger.info(f"[{self.AGENT_NAME}] validate start")

        errors = self._validate_common_result(result)
        if errors:
            error_message = "; ".join(errors)
            logger.warning(f"[{self.AGENT_NAME}] validate failed | {error_message}")
            return AgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                error=error_message,
            )

        logger.info(f"[{self.AGENT_NAME}] validate passed")
        return AgentResponse(
            agent_name=self.AGENT_NAME,
            result=result,
        )

    def _validate_common_result(self, result: Any) -> list[str]:
        if not isinstance(result, dict):
            return ["result must be a JSON object"]

        if not result:
            return ["result must not be empty"]

        errors: list[str] = []
        if "requirements" in result:
            errors.extend(self._validate_requirements(result["requirements"]))

        return errors

    def _validate_requirements(self, requirements: Any) -> list[str]:
        if not isinstance(requirements, list):
            return ["requirements must be a list"]

        if not requirements:
            return ["requirements must not be empty"]

        errors: list[str] = []
        for index, requirement in enumerate(requirements):
            item_path = f"requirements[{index}]"
            if not isinstance(requirement, dict):
                errors.append(f"{item_path} must be a JSON object")
                continue

            requirement_id = requirement.get("requirement_id") or requirement.get("id")
            if not requirement_id:
                errors.append(f"{item_path} must include requirement_id or id")

        return errors


validator_agent = ValidatorAgent()
