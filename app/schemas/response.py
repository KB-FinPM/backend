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
