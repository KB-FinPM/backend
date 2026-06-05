# EN: Standard input/output agent request and response contracts.
# KO: 사용자 입출력 표준화를 위한 Input/Output Agent 계약입니다.

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class InputType(StrEnum):
    TEXT = "TEXT"
    FILE = "FILE"
    MEETING_NOTES = "MEETING_NOTES"
    ARTIFACT_REQUEST = "ARTIFACT_REQUEST"


class NormalizedRequestType(StrEnum):
    DOCUMENT_INGESTION = "DOCUMENT_INGESTION"
    ARTIFACT_GENERATION = "ARTIFACT_GENERATION"
    SCHEDULE_TODO_EXTRACTION = "SCHEDULE_TODO_EXTRACTION"
    MEETING_ACTION_EXTRACTION = "MEETING_ACTION_EXTRACTION"
    CHAT_MESSAGE = "CHAT_MESSAGE"
    UNKNOWN = "UNKNOWN"


class OutputResponseType(StrEnum):
    API_RESPONSE = "API_RESPONSE"
    CHAT_RESPONSE = "CHAT_RESPONSE"
    ARTIFACT_EXPORT = "ARTIFACT_EXPORT"
    ERROR = "ERROR"


class InputFilePayload(BaseModel):
    file_name: str = Field(..., description="Original file name")
    file_bytes: bytes = Field(..., description="Uploaded file bytes")
    content_type: str | None = Field(None, description="Uploaded MIME type")


class InputAgentRequest(BaseModel):
    project_id: str = Field(..., description="Project ID")
    user_id: str | None = Field(None, description="User or actor ID")
    permission_scope: list[str] = Field(
        default_factory=list,
        description="Caller permission scope",
    )
    input_type: InputType = Field(..., description="Raw user input type")
    raw_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Original user request payload",
    )
    files: list[InputFilePayload] = Field(
        default_factory=list,
        description="Uploaded files",
    )
    context: dict[str, Any] = Field(default_factory=dict, description="Extra context")


class InputAgentResponse(BaseModel):
    success: bool = True
    agent_name: str = Field(..., description="Input agent name")
    normalized_request_type: NormalizedRequestType = Field(
        NormalizedRequestType.UNKNOWN,
        description="Internal normalized request type",
    )
    structured_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured internal JSON context",
    )
    validation_errors: list[str] = Field(
        default_factory=list,
        description="Input validation errors",
    )
    error: str | None = None


class OutputAgentRequest(BaseModel):
    project_id: str = Field(..., description="Project ID")
    response_type: OutputResponseType = Field(..., description="User response type")
    result_json: dict[str, Any] = Field(..., description="Internal result JSON")
    message: str = Field("ok", description="User-facing message")
    artifact: dict[str, Any] | None = Field(None, description="Artifact metadata")
    errors: list[str] = Field(default_factory=list, description="Error details")
    output_format: str = Field("markdown", description="Target output format")
    template: dict[str, Any] | None = Field(None, description="Resolved template")
    context: dict[str, Any] = Field(default_factory=dict, description="Extra context")


class OutputAgentResponse(BaseModel):
    success: bool = True
    agent_name: str = Field(..., description="Output agent name")
    message: str = Field("ok", description="User-facing message")
    display_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Payload suitable for API/UI display",
    )
    download_files: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Generated downloadable file descriptors",
    )
    artifact_refs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Referenced artifacts",
    )
    error: str | None = None
