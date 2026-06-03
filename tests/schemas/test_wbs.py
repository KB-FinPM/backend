# EN: Tests for minimal WBS artifact schema contracts.
# KO: WBS 최소 산출물 스키마 계약 테스트입니다.

import pytest
from pydantic import ValidationError

from app.schemas.wbs import WbsArtifact


def test_wbs_artifact_accepts_minimal_task_payload() -> None:
    artifact = WbsArtifact.model_validate(
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

    assert artifact.tasks[0].task_id == "WBS-001"
    assert artifact.tasks[0].metadata == {}


def test_wbs_artifact_rejects_missing_task_id() -> None:
    with pytest.raises(ValidationError):
        WbsArtifact.model_validate(
            {
                "artifact_type": "WBS",
                "tasks": [{"name": "Build login"}],
            }
        )
