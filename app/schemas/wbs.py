# EN: Minimal WBS artifact schema contract.
# KO: WBS 산출물의 최소 JSON 계약입니다.

from typing import Any

from pydantic import BaseModel, Field, model_validator


class WbsTask(BaseModel):
    task_id: str = Field(..., min_length=1, description="WBS task ID")
    name: str = Field(..., min_length=1, description="Task name")
    description: str | None = Field(None, description="Task description")
    source_requirement_ids: list[str] = Field(
        default_factory=list,
        description="Requirement IDs used to derive this task",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Agent-defined task metadata",
    )


class WbsArtifact(BaseModel):
    artifact_type: str = Field("WBS", description="Artifact type")
    tasks: list[WbsTask] = Field(..., min_length=1, description="WBS tasks")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Agent-defined artifact metadata",
    )

    @model_validator(mode="after")
    def validate_artifact_type(self) -> "WbsArtifact":
        if self.artifact_type != "WBS":
            raise ValueError("artifact_type must be WBS")

        return self
