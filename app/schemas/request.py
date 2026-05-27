from typing import Optional

from pydantic import BaseModel, Field


class UploadRequest(BaseModel):
    project_id: str = Field(..., description="Project ID")
    file_name: str = Field(..., description="Uploaded file name")


class GenerationRequest(BaseModel):
    project_id: str = Field(..., description="Project ID")
    document_ids: list[str] = Field(
        default_factory=list,
        description="Document IDs to use as generation context",
    )
    query: Optional[str] = Field(None, description="Additional generation request")
