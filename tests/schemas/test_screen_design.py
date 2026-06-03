# EN: Tests for minimal screen design artifact schema contracts.
# KO: 화면설계서 최소 산출물 스키마 계약 테스트입니다.

import pytest
from pydantic import ValidationError

from app.schemas.screen_design import ScreenDesignArtifact


def test_screen_design_artifact_accepts_minimal_screen_payload() -> None:
    artifact = ScreenDesignArtifact.model_validate(
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

    assert artifact.screens[0].screen_id == "SCR-001"
    assert artifact.screens[0].metadata == {}


def test_screen_design_artifact_rejects_missing_screen_id() -> None:
    with pytest.raises(ValidationError):
        ScreenDesignArtifact.model_validate(
            {
                "artifact_type": "SCREEN_DESIGN",
                "screens": [{"name": "Login screen"}],
            }
        )
