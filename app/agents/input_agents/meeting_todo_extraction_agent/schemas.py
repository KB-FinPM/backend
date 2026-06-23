from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MeetingDocumentSection(BaseModel):
    title: str = "본문"
    content: str = ""


class StructuredMeetingDocument(BaseModel):
    document_type: Literal["MEETING_MINUTES"] = "MEETING_MINUTES"
    meeting_title: str | None = None
    meeting_date: str | None = None
    meeting_place: str | None = None
    agenda: str | None = None
    attendees: list[str] = Field(default_factory=list)
    sections: list[MeetingDocumentSection] = Field(default_factory=list)


class MeetingTodoCandidate(BaseModel):
    candidate_id: str
    section_title: str | None = None
    source_sentence: str
    context_before: str | None = None
    context_after: str | None = None
    signals: list[str] = Field(default_factory=list)
    raw_assignee_hint: str | None = None
    raw_due_date_hint: str | None = None


class MeetingTodoItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str
    description: str = "회의록에서 추출된 TODO"
    assignee: str | None = None
    due_date: str | None = None
    due_date_text: str | None = None
    status: Literal["TODO", "NEEDS_CONFIRMATION"] = "NEEDS_CONFIRMATION"
    related_document: str = "회의록 기반 신규 TODO"
    source_type: Literal["MEETING_NOTE"] = "MEETING_NOTE"
    source_section: str | None = None
    source_sentence: str
    confidence: float = 0.6
    needs_confirmation: list[str] = Field(default_factory=list)
    classification: Literal["todo"] = "todo"


class MeetingTodoNonTodoCandidate(BaseModel):
    title: str
    classification: Literal["candidate", "issue_or_requirement", "not_todo"]
    reason: str
    source_sentence: str


class MeetingTodoExtractionResult(BaseModel):
    document_type: Literal["MEETING_MINUTES"] = "MEETING_MINUTES"
    meeting_date: str | None = None
    todo_items: list[MeetingTodoItem] = Field(default_factory=list)
    candidate_items: list[MeetingTodoNonTodoCandidate] = Field(default_factory=list)
    issue_items: list[dict[str, Any]] = Field(default_factory=list)
    requirement_candidates: list[dict[str, Any]] = Field(default_factory=list)
    decision_items: list[dict[str, Any]] = Field(default_factory=list)
    meeting_document: StructuredMeetingDocument | None = None
    candidates: list[MeetingTodoCandidate] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
