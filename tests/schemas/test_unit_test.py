# EN: Tests for minimal unit test artifact schema contracts.
# KO: 단위테스트케이스 최소 산출물 스키마 계약 테스트입니다.

import pytest
from pydantic import ValidationError

from app.schemas.unit_test import UnitTestArtifact


def test_unit_test_artifact_accepts_minimal_payload() -> None:
    artifact = UnitTestArtifact.model_validate(
        {
            "artifact_type": "UNITTEST_SPEC",
            "test_cases": [
                {
                    "test_case_id": "TEST-0001-001",
                    "test_case_name": "회원 조회 화면",
                    "requirement_id": "REQ-00001",
                    "requirement_name": "회원 조회",
                    "scenario_id": "Biz-0001",
                    "test_content": "회원 목록을 조회한다.",
                }
            ],
        }
    )

    assert artifact.test_cases[0].test_case_id == "TEST-0001-001"


def test_unit_test_artifact_rejects_wrong_artifact_type() -> None:
    with pytest.raises(ValidationError):
        UnitTestArtifact.model_validate(
            {
                "artifact_type": "WBS",
                "test_cases": [
                    {
                        "test_case_id": "TEST-0001-001",
                        "test_case_name": "회원 조회 화면",
                        "requirement_id": "REQ-00001",
                        "requirement_name": "회원 조회",
                        "scenario_id": "Biz-0001",
                        "test_content": "회원 목록을 조회한다.",
                    }
                ],
            }
        )
