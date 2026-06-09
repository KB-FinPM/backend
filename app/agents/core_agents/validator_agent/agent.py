# EN: Core agent for validating common generated artifact result rules.
# KO: 생성된 산출물 결과의 공통 규칙을 검증하는 Core Agent입니다.

from typing import Any

from app.core.logger import get_logger
from app.schemas.agent import AgentResponse
from app.schemas.requirement import RequirementArtifact
from app.schemas.schedule import ScheduleTodoList
from app.schemas.screen_design import ScreenDesignArtifact
from app.schemas.unit_test import UnitTestArtifact
from app.schemas.wbs import WbsArtifact

logger = get_logger(__name__)


class ValidatorAgent:
    """Validates common agent output rules before post-processing or storage."""

    AGENT_NAME = "ValidatorAgent"

    async def validate(self, result: Any) -> AgentResponse:
        logger.info(f"[{self.AGENT_NAME}] validate start")

        validated_result, errors = self._validate_common_result(result)
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
            result=validated_result,
        )

    def _validate_common_result(self, result: Any) -> tuple[Any, list[str]]:
        if not isinstance(result, dict):
            return result, ["result must be a JSON object"]

        if not result:
            return result, ["result must not be empty"]

        if "requirements" in result:
            return self._validate_requirement_artifact(result)

        if "tasks" in result:
            return self._validate_wbs_artifact(result)

        if "screens" in result:
            return self._validate_screen_design_artifact(result)

        if "test_cases" in result:
            return self._validate_unit_test_artifact(result)

        if "todos" in result:
            return self._validate_schedule_todo_list(result)

        return result, []

    def _validate_requirement_artifact(self, result: dict) -> tuple[dict, list[str]]:
        try:
            artifact = RequirementArtifact.model_validate(result)
        except ValueError as exc:
            return result, [str(exc)]

        return artifact.model_dump(mode="json"), []

    def _validate_schedule_todo_list(
        self,
        result: dict,
    ) -> tuple[dict, list[str]]:
        try:
            artifact = ScheduleTodoList.model_validate(result)
        except ValueError as exc:
            return result, [str(exc)]

        return artifact.model_dump(mode="json"), []

    def _validate_wbs_artifact(self, result: dict) -> tuple[dict, list[str]]:
        try:
            artifact = WbsArtifact.model_validate(result)
        except ValueError as exc:
            return result, [str(exc)]

        return artifact.model_dump(mode="json"), []

    def _validate_screen_design_artifact(
        self,
        result: dict,
    ) -> tuple[dict, list[str]]:
        try:
            artifact = ScreenDesignArtifact.model_validate(result)
        except ValueError as exc:
            return result, [str(exc)]

        return artifact.model_dump(mode="json"), []

    def _validate_unit_test_artifact(
        self,
        result: dict,
    ) -> tuple[dict, list[str]]:
        try:
            artifact = UnitTestArtifact.model_validate(result)
        except ValueError as exc:
            return result, [str(exc)]

        return artifact.model_dump(mode="json"), []


validator_agent = ValidatorAgent()
