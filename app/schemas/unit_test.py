# EN: Minimal unit test case artifact schema contract.
# KO: 단위테스트케이스 산출물의 최소 JSON 계약입니다.

from typing import Any

from pydantic import BaseModel, Field, model_validator


class UnitTestCase(BaseModel):
    test_case_id: str = Field(..., min_length=1, description="Unit test case ID")
    test_case_name: str = Field(..., min_length=1, description="Unit test case name")
    requirement_id: str = Field(..., min_length=1, description="Requirement ID")
    requirement_name: str = Field(..., min_length=1, description="Requirement name")
    scenario_id: str = Field(..., min_length=1, description="Scenario ID")
    test_content: str = Field(..., min_length=1, description="Unit test case content")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Agent-defined unit test metadata",
    )


class UnitTestArtifact(BaseModel):
    artifact_type: str = Field("UNITTEST_SPEC", description="Artifact type")
    test_cases: list[UnitTestCase] = Field(
        ...,
        min_length=1,
        description="Generated unit test cases",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Agent-defined artifact metadata",
    )

    @model_validator(mode="after")
    def validate_artifact_type(self) -> "UnitTestArtifact":
        if self.artifact_type != "UNITTEST_SPEC":
            raise ValueError("artifact_type must be UNITTEST_SPEC")

        return self
