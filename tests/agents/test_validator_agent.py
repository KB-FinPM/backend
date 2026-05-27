import pytest

from app.agents.core_agents.validator_agent.agent import ValidatorAgent


@pytest.mark.anyio
async def test_validator_accepts_raw_agent_result() -> None:
    validator = ValidatorAgent()

    response = await validator.validate({"raw": "LLM mock response"})

    assert response.success is True
    assert response.result == {"raw": "LLM mock response"}


@pytest.mark.anyio
async def test_validator_accepts_requirement_list_with_ids() -> None:
    validator = ValidatorAgent()

    response = await validator.validate(
        {
            "requirements": [
                {
                    "requirement_id": "RQ-001",
                    "description": "The user can sign in.",
                }
            ]
        }
    )

    assert response.success is True


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
    assert response.error == "requirements[0] must include requirement_id or id"
