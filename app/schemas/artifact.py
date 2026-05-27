from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class DocumentType(StrEnum):
    CONSTRUCTION_REQUIREMENT_DEFINITION = "CONSTRUCTION_REQUIREMENT_DEFINITION"
    REQUIREMENT_SPEC = "REQUIREMENT_SPEC"
    MEETING_NOTES = "MEETING_NOTES"
    UNKNOWN = "UNKNOWN"


class ArtifactType(StrEnum):
    REQUIREMENT_SPEC = "REQUIREMENT_SPEC"
    SCREEN_DESIGN = "SCREEN_DESIGN"
    WBS = "WBS"
    ACTION_ITEMS = "ACTION_ITEMS"


class TemplateReference(BaseModel):
    template_id: Optional[str] = Field(
        None,
        description="Template ID from admin UI or built-in template registry",
    )
    template_version: Optional[str] = Field(
        None,
        description="Template version to use for generation",
    )


class GenerationFlow(BaseModel):
    source_document_type: Optional[DocumentType] = Field(
        None,
        description="Type of source document used to generate the artifact",
    )
    target_artifact_type: ArtifactType = Field(
        ...,
        description="Type of artifact to generate",
    )
    template: TemplateReference = Field(
        default_factory=TemplateReference,
        description="Template selection for the generated artifact",
    )
