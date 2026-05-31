# EN: Requirement artifact schema contracts.
# KO: 요구사항 산출물 JSON 계약 스키마입니다.

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class RequirementPriority(StrEnum):
    MUST = "MUST"
    SHOULD = "SHOULD"
    COULD = "COULD"
    WONT = "WONT"


class RequirementItem(BaseModel):
    requirement_id: str = Field(..., min_length=1, description="Requirement ID")
    title: str = Field(..., min_length=1, description="Short requirement title")
    description: str = Field(..., min_length=1, description="Requirement description")
    priority: RequirementPriority = Field(
        RequirementPriority.SHOULD,
        description="MoSCoW priority",
    )
    source_document_id: str | None = Field(None, description="Source document ID")
    source_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Source chunk IDs used to derive this requirement",
    )
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description="Acceptance criteria",
    )
    rationale: str | None = Field(None, description="Generation rationale")


class RequirementArtifact(BaseModel):
    artifact_type: str = Field("REQUIREMENT_SPEC", description="Artifact type")
    requirements: list[RequirementItem] = Field(
        ...,
        min_length=1,
        description="Generated requirements",
    )
    metadata: dict = Field(default_factory=dict, description="Artifact metadata")

    @model_validator(mode="after")
    def validate_artifact_type(self) -> "RequirementArtifact":
        if self.artifact_type != "REQUIREMENT_SPEC":
            raise ValueError("artifact_type must be REQUIREMENT_SPEC")

        return self
