# EN: Traceability schema contracts for artifact relationships.
# KO: 산출물 관계 추적을 위한 스키마 계약입니다.

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ArtifactRelationType(StrEnum):
    DERIVED_FROM = "DERIVED_FROM"
    DECOMPOSED_TO = "DECOMPOSED_TO"
    DESIGNED_BY = "DESIGNED_BY"
    REFERENCES = "REFERENCES"
    IMPACTS = "IMPACTS"


class ArtifactLinkCreate(BaseModel):
    project_id: str = Field(..., description="Project ID")
    source_artifact_id: str = Field(..., description="Source artifact ID")
    source_item_id: str | None = Field(None, description="Source item ID")
    target_artifact_id: str = Field(..., description="Target artifact ID")
    target_item_id: str | None = Field(None, description="Target item ID")
    relation_type: ArtifactRelationType = Field(..., description="Relation type")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Relation metadata",
    )

    @model_validator(mode="after")
    def validate_distinct_artifacts(self) -> "ArtifactLinkCreate":
        if (
            self.source_artifact_id == self.target_artifact_id
            and self.source_item_id == self.target_item_id
        ):
            raise ValueError("source and target must not be the same artifact item")

        return self


class ArtifactLinkMetadata(ArtifactLinkCreate):
    link_id: str = Field(..., description="Artifact link ID")
