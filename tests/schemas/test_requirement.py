# EN: Tests for requirement artifact schema contracts.
# KO: 요구사항 산출물 스키마 계약 테스트입니다.

import pytest
from pydantic import ValidationError

from app.schemas.requirement import RequirementArtifact


def test_requirement_artifact_accepts_valid_payload() -> None:
    artifact = RequirementArtifact.model_validate(
        {
            "artifact_type": "REQUIREMENT_SPEC",
            "requirements": [
                {
                    "requirement_id": "RQ-001",
                    "title": "Sign in",
                    "description": "The user can sign in.",
                    "priority": "MUST",
                    "source_document_id": "DOC-001",
                    "source_chunk_ids": ["CHUNK-001"],
                    "acceptance_criteria": ["The user can sign in."],
                }
            ],
        }
    )

    assert artifact.requirements[0].requirement_id == "RQ-001"


def test_requirement_artifact_rejects_wrong_artifact_type() -> None:
    with pytest.raises(ValidationError):
        RequirementArtifact.model_validate(
            {
                "artifact_type": "WBS",
                "requirements": [
                    {
                        "requirement_id": "RQ-001",
                        "title": "Sign in",
                        "description": "The user can sign in.",
                    }
                ],
            }
        )
