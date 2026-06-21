# EN: Tests for common ValidatorAgent rules.
# KO: ValidatorAgent의 공통 검증 규칙을 확인하는 테스트입니다.

import pytest

from app.agents.core_agents.validator_agent.agent import ValidatorAgent
from app.schemas.artifact import ArtifactType


@pytest.mark.anyio
async def test_validator_rejects_unknown_object_without_expected_type() -> None:
    validator = ValidatorAgent()

    response = await validator.validate({"summary": "non requirement result"})

    assert response.success is False
    assert response.error == "result does not match a supported artifact schema"


@pytest.mark.anyio
async def test_validator_accepts_requirement_list_with_ids() -> None:
    validator = ValidatorAgent()

    response = await validator.validate(
        {
            "requirements": [
                {
                    "requirement_id": "RQ-001",
                    "title": "Sign in",
                    "description": "The user can sign in.",
                    "priority": "MUST",
                    "source_chunk_ids": ["CHUNK-001"],
                    "acceptance_criteria": ["The user can sign in."],
                }
            ]
        },
        expected_artifact_type=ArtifactType.REQUIREMENT_SPEC,
    )

    assert response.success is True
    assert response.result["artifact_type"] == "REQUIREMENT_SPEC"


@pytest.mark.anyio
async def test_validator_rejects_non_object_result() -> None:
    validator = ValidatorAgent()

    response = await validator.validate(["not", "a", "dict"])

    assert response.success is False
    assert response.error == "result must be a JSON object"


@pytest.mark.anyio
async def test_validator_rejects_empty_result() -> None:
    validator = ValidatorAgent()

    response = await validator.validate({})

    assert response.success is False
    assert response.error == "result must not be empty"


@pytest.mark.anyio
async def test_validator_rejects_requirement_without_id() -> None:
    validator = ValidatorAgent()

    response = await validator.validate(
        {
            "requirements": [
                {
                    "description": "The user can sign in.",
                }
            ]
        },
        expected_artifact_type=ArtifactType.REQUIREMENT_SPEC,
    )

    assert response.success is False
    assert response.error is not None
    assert "requirements.0.requirement_id" in response.error


@pytest.mark.anyio
async def test_validator_accepts_minimal_wbs_artifact() -> None:
    validator = ValidatorAgent()

    response = await validator.validate(
        {
            "artifact_type": "WBS",
            "tasks": [
                {
                    "task_id": "WBS-001",
                    "name": "Build login",
                    "source_requirement_ids": ["RQ-001"],
                }
            ],
        },
        expected_artifact_type=ArtifactType.WBS,
    )

    assert response.success is True
    assert response.result["artifact_type"] == "WBS"


@pytest.mark.anyio
async def test_validator_accepts_minimal_screen_design_artifact() -> None:
    validator = ValidatorAgent()

    response = await validator.validate(
        {
            "artifact_type": "SCREEN_DESIGN",
            "screens": [
                {
                    "screen_id": "SCR-001",
                    "name": "Login screen",
                    "source_requirement_ids": ["RQ-001"],
                }
            ],
        },
        expected_artifact_type=ArtifactType.SCREEN_DESIGN,
    )

    assert response.success is True
    assert response.result["artifact_type"] == "SCREEN_DESIGN"


@pytest.mark.anyio
async def test_validator_accepts_minimal_schedule_todo_list() -> None:
    validator = ValidatorAgent()

    response = await validator.validate(
        {
            "artifact_type": "SCHEDULE_TODO_LIST",
            "todos": [
                {
                    "todo_id": "TODO-001",
                    "title": "Confirm login scope",
                    "source_chunk_ids": ["CHUNK-001"],
                }
            ],
        }
    )

    assert response.success is True
    assert response.result["artifact_type"] == "SCHEDULE_TODO_LIST"


@pytest.mark.anyio
async def test_validator_accepts_minimal_unit_test_artifact() -> None:
    validator = ValidatorAgent()

    response = await validator.validate(
        {
            "artifact_type": "UNITTEST_SPEC",
            "test_cases": [
                {
                    "test_case_id": "TC-001",
                    "test_case_name": "Sign in succeeds",
                    "requirement_id": "RQ-001",
                    "requirement_name": "Sign in",
                    "scenario_id": "SCN-001",
                    "test_content": "Verify a valid user can sign in.",
                }
            ],
        },
        expected_artifact_type=ArtifactType.UNITTEST_SPEC,
    )

    assert response.success is True
    assert response.result["artifact_type"] == "UNITTEST_SPEC"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("artifact_type", "payload", "required_key"),
    [
        (ArtifactType.REQUIREMENT_SPEC, {"tasks": []}, "requirements"),
        (ArtifactType.WBS, {"requirements": []}, "tasks"),
        (ArtifactType.SCREEN_DESIGN, {"requirements": []}, "screens"),
        (ArtifactType.UNITTEST_SPEC, {"requirements": []}, "test_cases"),
    ],
)
async def test_validator_rejects_missing_key_for_expected_artifact_type(
    artifact_type: ArtifactType,
    payload: dict,
    required_key: str,
) -> None:
    validator = ValidatorAgent()

    response = await validator.validate(
        payload,
        expected_artifact_type=artifact_type,
    )

    assert response.success is False
    assert required_key in str(response.error)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "artifact_type",
    [
        ArtifactType.REQUIREMENT_SPEC,
        ArtifactType.WBS,
        ArtifactType.SCREEN_DESIGN,
        ArtifactType.UNITTEST_SPEC,
    ],
)
async def test_validator_rejects_empty_result_for_all_expected_artifact_types(
    artifact_type: ArtifactType,
) -> None:
    validator = ValidatorAgent()

    response = await validator.validate({}, expected_artifact_type=artifact_type)

    assert response.success is False
    assert response.error == "result must not be empty"
