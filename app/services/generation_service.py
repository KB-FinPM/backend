# EN: Business service for artifact generation use cases.

from dataclasses import dataclass, field
from typing import Any

from app.core.logger import get_logger
from app.orchestrator.generation_orchestrator import GenerationOrchestrator
from app.schemas.artifact import ArtifactType, DocumentType
from app.schemas.request import GenerationRequest
from app.schemas.response import GenerationResponse

logger = get_logger(__name__)


@dataclass(frozen=True)
class GenerationSourceValidationResult:
    """Shared source-document validation result for generation and chat flows."""

    project_id: str
    target_artifact_type: ArtifactType
    required_source_type: DocumentType | None = None
    allowed_source_types: list[DocumentType] = field(default_factory=list)
    source_document_required: bool = False
    missing_document_ids: list[str] = field(default_factory=list)
    invalid_type_documents: list[dict[str, str]] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not (
            self.source_document_required
            or self.missing_document_ids
            or self.invalid_type_documents
        )

    @property
    def error_code(self) -> str | None:
        if self.source_document_required:
            return "SOURCE_DOCUMENT_REQUIRED"
        if self.missing_document_ids:
            return "SOURCE_DOCUMENT_NOT_FOUND"
        if self.invalid_type_documents:
            return "INVALID_SOURCE_DOCUMENT_TYPE"
        return None

    @property
    def message(self) -> str:
        if self.source_document_required:
            return "source document is required"
        if self.missing_document_ids:
            return "source document not found"
        if self.invalid_type_documents and self.required_source_type is not None:
            return (
                f"{self.target_artifact_type.value} must be generated from "
                f"{self.required_source_type.value}"
            )
        if self.invalid_type_documents and self.allowed_source_types:
            allowed = ", ".join(source_type.value for source_type in self.allowed_source_types)
            return f"{self.target_artifact_type.value} must be generated from one of {allowed}"
        return "ok"

    @property
    def detail(self) -> dict[str, Any] | None:
        if self.source_document_required:
            return {
                "project_id": self.project_id,
                "target_artifact_type": self.target_artifact_type.value,
            }
        if self.missing_document_ids:
            return {
                "project_id": self.project_id,
                "missing_document_ids": self.missing_document_ids,
            }
        if self.invalid_type_documents:
            return {"documents": self.invalid_type_documents}
        return None


class GenerationService:
    """Keeps generation API routes stable while orchestrators evolve."""

    def __init__(self, orchestrator: GenerationOrchestrator) -> None:
        self.orchestrator = orchestrator

    def required_source_type_for(
        self,
        target_artifact_type: ArtifactType,
    ) -> DocumentType | None:
        if target_artifact_type in {
            ArtifactType.WBS,
            ArtifactType.UNITTEST_SPEC,
        }:
            return DocumentType.REQUIREMENT_SPEC
        return None

    def allowed_source_types_for(
        self,
        target_artifact_type: ArtifactType,
    ) -> list[DocumentType]:
        if target_artifact_type == ArtifactType.SCREEN_DESIGN:
            return [
                DocumentType.REQUIREMENT_SPEC,
                DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION,
            ]
        required_source_type = self.required_source_type_for(target_artifact_type)
        return [required_source_type] if required_source_type is not None else []

    async def validate_source_documents(
        self,
        request: GenerationRequest,
        *,
        document_service: Any,
        required_source_type: DocumentType | None = None,
    ) -> GenerationSourceValidationResult:
        target_artifact_type = request.generation_flow().target_artifact_type
        if required_source_type is None:
            required_source_type = self.required_source_type_for(target_artifact_type)
        allowed_source_types = (
            [required_source_type]
            if required_source_type is not None
            else self.allowed_source_types_for(target_artifact_type)
        )

        if not request.source_document_ids:
            return GenerationSourceValidationResult(
                project_id=request.project_id,
                target_artifact_type=target_artifact_type,
                required_source_type=required_source_type,
                allowed_source_types=allowed_source_types,
                source_document_required=True,
            )

        missing_document_ids: list[str] = []
        invalid_type_documents: list[dict[str, str]] = []
        for document_id in request.source_document_ids:
            document = await document_service.get_document(
                project_id=request.project_id,
                document_id=document_id,
            )
            if document is None:
                missing_document_ids.append(document_id)
                continue

            if allowed_source_types and document.document_type not in allowed_source_types:
                invalid_detail = {
                    "document_id": document.document_id,
                    "document_type": document.document_type.value,
                }
                if len(allowed_source_types) == 1:
                    invalid_detail["required_document_type"] = allowed_source_types[0].value
                else:
                    invalid_detail["required_document_types"] = [
                        source_type.value for source_type in allowed_source_types
                    ]
                invalid_type_documents.append(
                    invalid_detail
                )

        return GenerationSourceValidationResult(
            project_id=request.project_id,
            target_artifact_type=target_artifact_type,
            required_source_type=required_source_type,
            allowed_source_types=allowed_source_types,
            missing_document_ids=missing_document_ids,
            invalid_type_documents=invalid_type_documents,
        )

    async def generate_requirement(
        self,
        request: GenerationRequest,
        *,
        artifact_service: Any,
        retrieval_service: Any = None,
        template_service: Any = None,
        document_service: Any = None,
    ) -> GenerationResponse:
        logger.info(
            f"!!! GenerationService generate_requirement | project_id={request.project_id} | "
            f"target_artifact_type={request.target_artifact_type.value} | "
            f"source_document_type={request.source_document_type or 'UNKNOWN'} | "
            f"source_document_ids={request.source_document_ids or []}"
        )
        return await self.orchestrator.generate_requirement(
            request,
            artifact_service=artifact_service,
            retrieval_service=retrieval_service,
            template_service=template_service,
            document_service=document_service,
        )

    async def generate_artifact(
        self,
        request: GenerationRequest,
        *,
        artifact_service: Any,
        retrieval_service: Any = None,
        template_service: Any = None,
        document_service: Any = None,
    ) -> GenerationResponse:
        logger.info(
            f"!!! GenerationService generate_artifact | project_id={request.project_id} | "
            f"target_artifact_type={request.target_artifact_type.value} | "
            f"source_document_type={request.source_document_type or 'UNKNOWN'} | "
            f"source_document_ids={request.source_document_ids or []}"
        )
        return await self.orchestrator.generate_artifact(
            request,
            artifact_service=artifact_service,
            retrieval_service=retrieval_service,
            template_service=template_service,
            document_service=document_service,
        )
