from pydantic import BaseModel, Field
from typing import Any, Optional


class BaseResponse(BaseModel):
    success: bool = True
    message: str = "ok"


class ErrorResponse(BaseResponse):
    success: bool = False
    error_code: Optional[str] = None
    detail: Optional[str] = None


class GenerationResponse(BaseResponse):
    project_id: str
    result: Any = Field(None, description="생성된 결과 JSON")
