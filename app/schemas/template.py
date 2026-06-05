# EN: Artifact template schema contracts.
# KO: 산출물 템플릿 JSON 계약 스키마입니다.

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.artifact import ArtifactType


class TemplateMetadata(BaseModel):
    template_id: str = Field(..., description="Template ID")
    template_version: str = Field(..., description="Template version")
    artifact_type: ArtifactType = Field(..., description="Target artifact type")
    name: str = Field(..., description="Template display name")
    content: str | dict[str, Any] = Field(
        ...,
        description="Template body or instruction content",
    )
    placeholders: dict[str, Any] = Field(
        default_factory=dict,
        description="Template placeholders and default values",
    )
    is_builtin: bool = Field(False, description="Whether the template is built in")
