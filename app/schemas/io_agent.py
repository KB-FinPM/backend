# EN: Common input/output agent request and response contracts.
# KO: Input/Output Agent 공통 요청/응답 계약입니다.

from typing import Any

from pydantic import BaseModel, Field


class InputAgentRequest(BaseModel):
    project_id: str = Field(..., description="Project ID")
    file_name: str = Field(..., description="Original file name")
    file_bytes: bytes = Field(..., description="Uploaded file bytes")
    content_type: str | None = Field(None, description="Uploaded MIME type")
    context: dict[str, Any] = Field(default_factory=dict, description="Extra context")


class InputAgentResponse(BaseModel):
    success: bool = True
    agent_name: str = Field(..., description="Input agent name")
    result: dict[str, Any] | None = Field(None, description="Structured parsed result")
    error: str | None = None


class OutputAgentRequest(BaseModel):
    project_id: str = Field(..., description="Project ID")
    artifact_id: str | None = Field(None, description="Artifact ID")
    artifact_type: str = Field(..., description="Artifact type")
    result_json: dict[str, Any] = Field(..., description="Structured artifact JSON")
    output_format: str = Field("markdown", description="Target output format")
    template: dict[str, Any] | None = Field(None, description="Resolved template")
    context: dict[str, Any] = Field(default_factory=dict, description="Extra context")


class OutputAgentResponse(BaseModel):
    success: bool = True
    agent_name: str = Field(..., description="Output agent name")
    result: dict[str, Any] | None = Field(None, description="Output artifact metadata")
    error: str | None = None
