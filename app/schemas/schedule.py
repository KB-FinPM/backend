# EN: Minimal meeting-action-item schema contract.
# KO: 일정관리 todo 결과의 최소 JSON 계약입니다.

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScheduleTodoItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    todo_id: str = Field(..., min_length=1, description="Todo item ID")
    project_id: str | None = Field(None, description="Project ID")
    title: str = Field(..., min_length=1, description="Todo title")
    description: str | None = Field(None, description="Todo description")
    assignee: str | None = Field(None, description="Assignee name or ID")
    due_date: str | None = Field(None, description="Due date as text or ISO-like string")
    related_artifact: str | None = Field(None, description="Related PM artifact")
    related_document: str | None = Field(None, description="Related artifact/document")
    source_type: str = Field("MEETING_MINUTES", description="TODO source type")
    status: str = Field("TODO", description="TODO status")
    source_document_id: str | None = Field(None, description="Source document ID")
    source_artifact_id: str | None = Field(None, description="Source artifact ID")
    source_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Source chunk IDs used to derive this todo",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Agent-defined todo metadata",
    )


class ScheduleTodoList(BaseModel):
    model_config = ConfigDict(extra="allow")

    artifact_type: str = Field(
        "SCHEDULE_TODO_LIST",
        description="Meeting action-item extraction result type",
    )
    action: str | None = Field(None, description="Schedule management action")
    status: str = Field("SUCCESS", description="Schedule action result status")
    todos: list[ScheduleTodoItem] = Field(
        default_factory=list,
        description="Action items extracted from meeting notes",
    )
    needs_confirmation: list[ScheduleTodoItem] = Field(
        default_factory=list,
        description="Schedule items that require missing assignee or due date confirmation",
    )
    needs_confirmation_count: int = Field(
        0,
        description="Number of extracted or matched items that need confirmation",
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Fields required to complete the schedule action",
    )
    candidates: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Candidate todos for ambiguous follow-up actions",
    )
    week_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Calculated project week context",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Agent-defined result metadata",
    )

    @model_validator(mode="after")
    def validate_artifact_type(self) -> "ScheduleTodoList":
        if self.artifact_type != "SCHEDULE_TODO_LIST":
            raise ValueError("artifact_type must be SCHEDULE_TODO_LIST")

        return self
