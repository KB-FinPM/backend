from pydantic import BaseModel, Field
from typing import Optional


class UploadRequest(BaseModel):
    project_id: str = Field(..., description="프로젝트 ID")
    file_name: str = Field(..., description="업로드 파일명")


class GenerationRequest(BaseModel):
    project_id: str = Field(..., description="프로젝트 ID")
    document_ids: list[str] = Field(default=[], description="참조할 문서 ID 목록")
    query: Optional[str] = Field(None, description="추가 요청사항")
