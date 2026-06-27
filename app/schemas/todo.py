from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


TodoStatus = Literal["NOT_STARTED", "IN_PROGRESS", "DONE"]
TodoSourceType = Literal["MEETING_NOTES", "WBS", "MANUAL"]


class TodoItem(BaseModel):
    todo_id: str
    title: str
    assignee: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    due_date: str | None = None
    due_date_text: str | None = None
    status: TodoStatus = "NOT_STARTED"
    source_type: TodoSourceType = "MEETING_NOTES"
    source_document_id: str | None = None
    source_document_name: str | None = None
    related_document: str | None = None
    description: str | None = None
    source_sentence: str | None = None
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None


class TodoListResponse(BaseModel):
    items: list[TodoItem] = Field(default_factory=list)


class TodoUpdateRequest(BaseModel):
    title: str | None = None
    assignee: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    due_date: str | None = None
    status: TodoStatus | None = None
    description: str | None = None


class TodoImportPreviewRequest(BaseModel):
    document_id: str
    document_type: TodoSourceType


class TodoDuplicateItem(BaseModel):
    candidate: TodoItem
    matched_existing: TodoItem
    duplicate_level: Literal["DUPLICATE_HIGH", "DUPLICATE_POSSIBLE"]


class TodoImportPreviewResponse(BaseModel):
    new_items: list[TodoItem] = Field(default_factory=list)
    duplicate_items: list[TodoDuplicateItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TodoImportCommitRequest(BaseModel):
    items: list[TodoItem] = Field(default_factory=list)
    duplicate_decisions: list[dict[str, str]] = Field(default_factory=list)


class TodoImportCommitResponse(BaseModel):
    saved_items: list[TodoItem] = Field(default_factory=list)
    skipped_items: list[TodoItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
