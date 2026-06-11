# EN: Common API response schemas.
# KO: API 공통 응답 스키마입니다.

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas.artifact import DocumentMetadata


class BaseResponse(BaseModel):
    success: bool = True
    message: str = "ok"


class ErrorResponse(BaseResponse):
    success: bool = False
    error_code: Optional[str] = None
    detail: Any = None


class GenerationResponse(BaseResponse):
    project_id: str
    document_id: Optional[str] = Field(
        None,
        description="Generated document ID when the artifact export registers a document",
    )
    document_type: Optional[str] = Field(
        None,
        description="Generated document type when the artifact export registers a document",
    )
    result: Any = Field(None, description="Generated artifact result JSON")


class ScheduleTodoResponse(BaseResponse):
    project_id: str
    result: Any = Field(None, description="Extracted schedule todo result JSON")
    display: dict[str, Any] = Field(
        default_factory=dict,
        description="Output-agent formatted API/UI display payload",
    )


class DocumentUploadResponse(BaseResponse):
    document: DocumentMetadata
    display: dict[str, Any] = Field(
        default_factory=dict,
        description="Output-agent formatted API/UI display payload",
    )
