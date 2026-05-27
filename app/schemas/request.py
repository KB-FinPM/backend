from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.schemas.artifact import ArtifactType, DocumentType, GenerationFlow, TemplateReference


class UploadRequest(BaseModel):
    project_id: str = Field(..., description="Project ID")
    file_name: str = Field(..., description="Uploaded file name")


class GenerationRequest(BaseModel):
    project_id: str = Field(..., description="Project ID")
    source_document_ids: list[str] = Field(
        default_factory=list,
        description="Source document IDs used to generate the target artifact",
    )
    document_ids: list[str] = Field(
        default_factory=list,
        description="Deprecated alias for source_document_ids",
    )
    source_document_type: Optional[DocumentType] = Field(
        None,
        description="Type of source document used to generate the target artifact",
    )
    target_artifact_type: ArtifactType = Field(
        ArtifactType.REQUIREMENT_SPEC,
        description="Type of artifact to generate",
    )
    template_id: Optional[str] = Field(
        None,
        description="Template ID from admin UI or built-in template registry",
    )
    template_version: Optional[str] = Field(
        None,
        description="Template version to use for generation",
    )
    query: Optional[str] = Field(None, description="Additional generation request")

    @model_validator(mode="after")
    def sync_document_id_aliases(self) -> "GenerationRequest":
        if not self.source_document_ids and self.document_ids:
            self.source_document_ids = list(self.document_ids)

        if not self.document_ids and self.source_document_ids:
            self.document_ids = list(self.source_document_ids)

        return self

    def generation_flow(self) -> GenerationFlow:
        return GenerationFlow(
            source_document_type=self.source_document_type,
            target_artifact_type=self.target_artifact_type,
            template=TemplateReference(
                template_id=self.template_id,
                template_version=self.template_version,
            ),
        )
