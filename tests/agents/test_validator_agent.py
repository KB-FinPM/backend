# EN: Tests for common ValidatorAgent rules.
# KO: ValidatorAgent의 공통 검증 규칙을 확인하는 테스트입니다.

import pytest

from app.agents.core_agents.validator_agent.agent import ValidatorAgent


@pytest.mark.anyio
async def test_validator_accepts_non_requirement_object() -> None:
    validator = ValidatorAgent()

    response = await validator.validate({"summary": "non requirement result"})

    assert response.success is True
    assert response.result == {"summary": "non requirement result"}


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
        }
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
        }
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
        }
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
        }
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
