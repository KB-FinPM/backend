from __future__ import annotations

import pytest

from app.agents.core_agents.validator_agent.agent import ValidatorAgent
from app.schemas.artifact import ArtifactType


@pytest.mark.anyio
async def test_validator_rejects_artifact_type_mismatch() -> None:
    response = await ValidatorAgent().validate(
        {
            "artifact_type": "WBS",
            "requirements": [
                {
                    "requirement_id": "REQ-001",
                    "title": "Login",
                    "description": "Users can sign in.",
                }
            ],
        },
        expected_artifact_type=ArtifactType.REQUIREMENT_SPEC,
    )

    assert response.success is False
    assert "artifact_type" in response.error


@pytest.mark.anyio
async def test_validator_returns_failure_for_unknown_expected_artifact_type() -> None:
    response = await ValidatorAgent().validate(
        {"requirements": []},
        expected_artifact_type="NOT_REAL",
    )

    assert response.success is False
    assert "unsupported artifact type" in response.error


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("artifact_type", "payload", "duplicate_field"),
    [
        (
            ArtifactType.REQUIREMENT_SPEC,
            {
                "artifact_type": "REQUIREMENT_SPEC",
                "requirements": [
                    {"requirement_id": "REQ-001", "title": "A", "description": "A"},
                    {"requirement_id": "REQ-001", "title": "B", "description": "B"},
                ],
            },
            "requirement_id",
        ),
        (
            ArtifactType.WBS,
            {
                "artifact_type": "WBS",
                "tasks": [
                    {"task_id": "WBS-001", "name": "A", "source_requirement_ids": ["REQ-001"]},
                    {"task_id": "WBS-001", "name": "B", "source_requirement_ids": ["REQ-002"]},
                ],
            },
            "task_id",
        ),
        (
            ArtifactType.SCREEN_DESIGN,
            {
                "artifact_type": "SCREEN_DESIGN",
                "screens": [
                    {"screen_id": "SCR-001", "name": "A", "source_requirement_ids": ["REQ-001"]},
                    {"screen_id": "SCR-001", "name": "B", "source_requirement_ids": ["REQ-002"]},
                ],
            },
            "screen_id",
        ),
        (
            ArtifactType.UNITTEST_SPEC,
            {
                "artifact_type": "UNITTEST_SPEC",
                "test_cases": [
                    {
                        "test_case_id": "TC-001",
                        "test_case_name": "A",
                        "requirement_id": "REQ-001",
                        "requirement_name": "Login",
                        "scenario_id": "SCN-001",
                        "test_content": "Run test",
                    },
                    {
                        "test_case_id": "TC-001",
                        "test_case_name": "B",
                        "requirement_id": "REQ-002",
                        "requirement_name": "Logout",
                        "scenario_id": "SCN-002",
                        "test_content": "Run test",
                    },
                ],
            },
            "test_case_id",
        ),
    ],
)
async def test_validator_rejects_duplicate_item_ids(
    artifact_type: ArtifactType,
    payload: dict,
    duplicate_field: str,
) -> None:
    response = await ValidatorAgent().validate(
        payload,
        expected_artifact_type=artifact_type,
    )

    assert response.success is False
    assert duplicate_field in response.error


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("artifact_type", "payload", "field"),
    [
        (
            ArtifactType.WBS,
            {"artifact_type": "WBS", "tasks": [{"task_id": "WBS-001", "name": "A"}]},
            "source_requirement_ids",
        ),
        (
            ArtifactType.SCREEN_DESIGN,
            {
                "artifact_type": "SCREEN_DESIGN",
                "screens": [{"screen_id": "SCR-001", "name": "A"}],
            },
            "source_requirement_ids",
        ),
    ],
)
async def test_validator_rejects_downstream_items_without_source_mapping(
    artifact_type: ArtifactType,
    payload: dict,
    field: str,
) -> None:
    response = await ValidatorAgent().validate(
        payload,
        expected_artifact_type=artifact_type,
    )

    assert response.success is False
    assert field in response.error
