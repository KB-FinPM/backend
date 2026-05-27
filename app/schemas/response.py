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
    detail: Optional[str] = None


class GenerationResponse(BaseResponse):
    project_id: str
    result: Any = Field(None, description="Generated artifact result JSON")


class DocumentUploadResponse(BaseResponse):
    document: DocumentMetadata
