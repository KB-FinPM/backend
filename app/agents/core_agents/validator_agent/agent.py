# EN: Core agent for validating common generated artifact result rules.
# KO: 생성된 산출물 결과의 공통 규칙을 검증하는 Core Agent입니다.

from typing import Any

from app.core.logger import get_logger
from app.schemas.agent import AgentResponse
from app.schemas.artifact import ArtifactType
from app.schemas.requirement import RequirementArtifact
from app.schemas.schedule import ScheduleTodoList
from app.schemas.screen_design import ScreenDesignArtifact
from app.schemas.unit_test import UnitTestArtifact
from app.schemas.wbs import WbsArtifact

logger = get_logger(__name__)


class ValidatorAgent:
    """Validates common agent output rules before post-processing or storage."""

    AGENT_NAME = "ValidatorAgent"

    async def validate(
        self,
        result: Any,
        *,
        expected_artifact_type: ArtifactType | str | None = None,
    ) -> AgentResponse:
        logger.info(f"[{self.AGENT_NAME}] validate start")

        try:
            validated_result, errors = self._validate_common_result(
                result,
                expected_artifact_type=expected_artifact_type,
            )
        except ValueError as exc:
            validated_result = result
            errors = [str(exc)]
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

    def _validate_common_result(
        self,
        result: Any,
        *,
        expected_artifact_type: ArtifactType | str | None = None,
    ) -> tuple[Any, list[str]]:
        if not isinstance(result, dict):
            return result, ["result must be a JSON object"]

        if not result:
            return result, ["result must not be empty"]

        normalized_expected_type = self._normalize_artifact_type(
            expected_artifact_type,
        )
        if normalized_expected_type is not None:
            return self._validate_expected_artifact(
                result,
                normalized_expected_type,
            )

        if "requirements" in result:
            return self._validate_requirement_artifact(result)

        if "tasks" in result:
            return self._validate_wbs_artifact(result)

        if "screens" in result:
            return self._validate_screen_design_artifact(result)

        if "test_cases" in result:
            return self._validate_unit_test_artifact(result)

        if "todos" in result or self._looks_like_schedule_result(result):
            return self._validate_schedule_todo_list(result)

        return result, ["result does not match a supported artifact schema"]

    def _looks_like_schedule_result(self, result: dict) -> bool:
        if result.get("artifact_type") == "SCHEDULE_TODO_LIST":
            return True
        action = str(result.get("action") or "")
        status = str(result.get("status") or "")
        return bool(action and status and action.startswith(("SHOW_", "COMPLETE_", "EXTRACT_", "COMPARE_", "ASSISTANT_")))

    def _normalize_artifact_type(
        self,
        artifact_type: ArtifactType | str | None,
    ) -> ArtifactType | None:
        if artifact_type is None:
            return None
        if isinstance(artifact_type, ArtifactType):
            return artifact_type
        try:
            return ArtifactType(str(artifact_type))
        except ValueError as exc:
            raise ValueError(f"unsupported artifact type: {artifact_type}") from exc

    def _validate_expected_artifact(
        self,
        result: dict,
        expected_artifact_type: ArtifactType,
    ) -> tuple[dict, list[str]]:
        validators = {
            ArtifactType.REQUIREMENT_SPEC: (
                "requirements",
                self._validate_requirement_artifact,
            ),
            ArtifactType.WBS: ("tasks", self._validate_wbs_artifact),
            ArtifactType.SCREEN_DESIGN: (
                "screens",
                self._validate_screen_design_artifact,
            ),
            ArtifactType.UNITTEST_SPEC: (
                "test_cases",
                self._validate_unit_test_artifact,
            ),
            ArtifactType.ACTION_ITEMS: (
                "todos",
                self._validate_schedule_todo_list,
            ),
        }
        required_key, validator = validators[expected_artifact_type]
        if required_key not in result:
            return result, [
                f"{expected_artifact_type.value} result must include '{required_key}'"
            ]
        return validator(result)

    def _validate_requirement_artifact(self, result: dict) -> tuple[dict, list[str]]:
        try:
            artifact = RequirementArtifact.model_validate(result)
        except ValueError as exc:
            return result, [str(exc)]

        errors = self._duplicate_field_errors(
            artifact.requirements,
            "requirement_id",
        )
        return artifact.model_dump(mode="json"), errors

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

        errors = self._duplicate_field_errors(artifact.tasks, "task_id")
        errors.extend(
            self._required_non_empty_list_errors(
                artifact.tasks,
                item_id_field="task_id",
                required_field="source_requirement_ids",
            )
        )
        return artifact.model_dump(mode="json"), errors

    def _validate_screen_design_artifact(
        self,
        result: dict,
    ) -> tuple[dict, list[str]]:
        try:
            artifact = ScreenDesignArtifact.model_validate(result)
        except ValueError as exc:
            return result, [str(exc)]

        errors = self._duplicate_field_errors(artifact.screens, "screen_id")
        errors.extend(
            self._required_non_empty_list_errors(
                artifact.screens,
                item_id_field="screen_id",
                required_field="source_requirement_ids",
            )
        )
        return artifact.model_dump(mode="json"), errors

    def _validate_unit_test_artifact(
        self,
        result: dict,
    ) -> tuple[dict, list[str]]:
        try:
            artifact = UnitTestArtifact.model_validate(result)
        except ValueError as exc:
            return result, [str(exc)]

        errors = self._duplicate_field_errors(artifact.test_cases, "test_case_id")
        return artifact.model_dump(mode="json"), errors

    def _duplicate_field_errors(self, items: list[Any], field_name: str) -> list[str]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for item in items:
            value = str(getattr(item, field_name, "") or "")
            if not value:
                continue
            if value in seen:
                duplicates.add(value)
            seen.add(value)
        if not duplicates:
            return []
        duplicate_values = ", ".join(sorted(duplicates))
        return [f"{field_name} must be unique: {duplicate_values}"]

    def _required_non_empty_list_errors(
        self,
        items: list[Any],
        *,
        item_id_field: str,
        required_field: str,
    ) -> list[str]:
        missing = [
            str(getattr(item, item_id_field, "") or "<unknown>")
            for item in items
            if not getattr(item, required_field, [])
        ]
        if not missing:
            return []
        missing_values = ", ".join(missing)
        return [f"{required_field} must be provided for: {missing_values}"]


validator_agent = ValidatorAgent()
