# EN: Minimal schedule-management/todo schema contract.
# KO: 일정관리 todo 결과의 최소 JSON 계약입니다.

from typing import Any

from pydantic import BaseModel, Field, model_validator


class ScheduleTodoItem(BaseModel):
    todo_id: str = Field(..., min_length=1, description="Todo item ID")
    title: str = Field(..., min_length=1, description="Todo title")
    description: str | None = Field(None, description="Todo description")
    assignee: str | None = Field(None, description="Assignee name or ID")
    due_date: str | None = Field(None, description="Due date as an ISO-like string")
    source_document_id: str | None = Field(None, description="Source document ID")
    source_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Source chunk IDs used to derive this todo",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Agent-defined todo metadata",
    )


class ScheduleTodoList(BaseModel):
    artifact_type: str = Field(
        "SCHEDULE_TODO_LIST",
        description="Schedule-management result type",
    )
    todos: list[ScheduleTodoItem] = Field(
        ...,
        min_length=1,
        description="Todo items extracted from meeting notes or context",
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
