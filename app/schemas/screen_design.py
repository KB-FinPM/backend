# EN: Minimal screen design artifact schema contract.
# KO: 화면설계서 산출물의 최소 JSON 계약입니다.

from typing import Any

from pydantic import BaseModel, Field, model_validator


class ScreenDefinition(BaseModel):
    screen_id: str = Field(..., min_length=1, description="Screen ID")
    name: str = Field(..., min_length=1, description="Screen name")
    description: str | None = Field(None, description="Screen description")
    source_requirement_ids: list[str] = Field(
        default_factory=list,
        description="Requirement IDs used to derive this screen",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Agent-defined screen metadata",
    )


class ScreenDesignArtifact(BaseModel):
    artifact_type: str = Field("SCREEN_DESIGN", description="Artifact type")
    screens: list[ScreenDefinition] = Field(
        ...,
        min_length=1,
        description="Screen definitions",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Agent-defined artifact metadata",
    )

    @model_validator(mode="after")
    def validate_artifact_type(self) -> "ScreenDesignArtifact":
        if self.artifact_type != "SCREEN_DESIGN":
            raise ValueError("artifact_type must be SCREEN_DESIGN")

        return self
