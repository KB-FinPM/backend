# EN: Generation API routes delegate artifact generation requests to orchestrators.
# KO: 산출물 생성 API 라우터이며 요청 처리를 오케스트레이터에 위임합니다.

from fastapi import APIRouter, Body, Depends, status

from app.core.exceptions import ApiError
from app.core.logger import get_logger
from app.dependencies import (
    get_artifact_service,
    get_document_service,
    get_generation_service,
    get_input_orchestrator,
    get_output_orchestrator,
    get_retrieval_service,
    get_template_service,
)
from app.orchestrator.input_orchestrator import InputOrchestrator
from app.orchestrator.output_orchestrator import OutputOrchestrator
from app.rag.retrieval import RetrievalService
from app.schemas.artifact import ArtifactType, DocumentType
from app.schemas.io_agent import (
    InputAgentRequest,
    InputAgentResponse,
    InputType,
    OutputAgentRequest,
    OutputResponseType,
)
from app.schemas.request import GenerationRequest
from app.schemas.response import ErrorResponse, GenerationResponse
from app.services.artifact_service import ArtifactService
from app.services.document_service import DocumentService
from app.services.generation_service import GenerationService
from app.services.template_service import TemplateService

logger = get_logger(__name__)
router = APIRouter()

GENERATION_ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}

REQUIREMENT_EXAMPLE = {
    "summary": "Build requirement spec from construction requirement definition",
    "value": {
        "project_id": "PRJ-001",
        "source_document_ids": ["DOC-CONST-001"],
        "source_document_type": "CONSTRUCTION_REQUIREMENT_DEFINITION",
        "target_artifact_type": "REQUIREMENT_SPEC",
        "template_id": "TPL-REQ-SPEC-DEFAULT",
        "query": "Create a requirement specification.",
        "permission_scope": ["project:read"],
    },
}

WBS_EXAMPLE = {
    "summary": "Build WBS from requirement specification",
    "value": {
        "project_id": "PRJ-001",
        "source_document_ids": ["DOC-REQ-001"],
        "source_document_type": "REQUIREMENT_SPEC",
        "target_artifact_type": "WBS",
        "query": "Create a WBS from the requirement specification.",
        "permission_scope": ["project:read"],
    },
}

SCREEN_DESIGN_EXAMPLE = {
    "summary": "Build screen design from requirement specification",
    "value": {
        "project_id": "PRJ-001",
        "source_document_ids": ["DOC-REQ-001"],
        "source_document_type": "REQUIREMENT_SPEC",
        "target_artifact_type": "SCREEN_DESIGN",
        "query": "Create a screen design document from the requirement specification.",
        "permission_scope": ["project:read"],
    },
}


@router.post(
    "/requirement",
    response_model=GenerationResponse,
    responses=GENERATION_ERROR_RESPONSES,
)
async def generate_requirement(
    request: GenerationRequest = Body(
        ...,
        openapi_examples={"requirement": REQUIREMENT_EXAMPLE},
    ),
    generation_service: GenerationService = Depends(get_generation_service),
    artifact_service: ArtifactService = Depends(get_artifact_service),
    document_service: DocumentService = Depends(get_document_service),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    template_service: TemplateService = Depends(get_template_service),
    input_orchestrator: InputOrchestrator = Depends(get_input_orchestrator),
    output_orchestrator: OutputOrchestrator = Depends(get_output_orchestrator),
) -> GenerationResponse:
    """Generate a requirement artifact through the PM agent orchestrator."""
    logger.info(f"generate_requirement | project_id={request.project_id}")

    await _validate_source_documents(
        request=request,
        document_service=document_service,
    )
    input_response = await _normalize_generation_input(request, input_orchestrator)
    if not input_response.success:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="GENERATION_INPUT_NORMALIZATION_FAILED",
            message=input_response.error or "generation input normalization failed",
            detail={"errors": input_response.validation_errors},
        )
    response = await generation_service.generate_artifact(
        request,
        artifact_service=artifact_service,
        retrieval_service=retrieval_service,
        template_service=template_service,
    )
    return await _format_generation_response(response, output_orchestrator)


@router.post(
    "/wbs",
    response_model=GenerationResponse,
    responses=GENERATION_ERROR_RESPONSES,
)
async def generate_wbs(
    request: GenerationRequest = Body(..., openapi_examples={"wbs": WBS_EXAMPLE}),
    generation_service: GenerationService = Depends(get_generation_service),
    artifact_service: ArtifactService = Depends(get_artifact_service),
    document_service: DocumentService = Depends(get_document_service),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    template_service: TemplateService = Depends(get_template_service),
    input_orchestrator: InputOrchestrator = Depends(get_input_orchestrator),
    output_orchestrator: OutputOrchestrator = Depends(get_output_orchestrator),
) -> GenerationResponse:
    """Generate a WBS artifact through the PM agent orchestrator."""
    logger.info(f"generate_wbs | project_id={request.project_id}")
    request.target_artifact_type = ArtifactType.WBS
    request.source_document_type = request.source_document_type or (
        DocumentType.REQUIREMENT_SPEC
    )

    await _validate_source_documents(
        request=request,
        document_service=document_service,
        required_source_type=DocumentType.REQUIREMENT_SPEC,
    )
    input_response = await _normalize_generation_input(request, input_orchestrator)
    if not input_response.success:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="GENERATION_INPUT_NORMALIZATION_FAILED",
            message=input_response.error or "generation input normalization failed",
            detail={"errors": input_response.validation_errors},
        )
    response = await generation_service.generate_artifact(
        request,
        artifact_service=artifact_service,
        retrieval_service=retrieval_service,
        template_service=template_service,
    )
    return await _format_generation_response(response, output_orchestrator)


@router.post(
    "/screen-design",
    response_model=GenerationResponse,
    responses=GENERATION_ERROR_RESPONSES,
)
async def generate_screen_design(
    request: GenerationRequest = Body(
        ...,
        openapi_examples={"screen_design": SCREEN_DESIGN_EXAMPLE},
    ),
    generation_service: GenerationService = Depends(get_generation_service),
    artifact_service: ArtifactService = Depends(get_artifact_service),
    document_service: DocumentService = Depends(get_document_service),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    template_service: TemplateService = Depends(get_template_service),
    input_orchestrator: InputOrchestrator = Depends(get_input_orchestrator),
    output_orchestrator: OutputOrchestrator = Depends(get_output_orchestrator),
) -> GenerationResponse:
    """Generate a screen design artifact through the PM agent orchestrator."""
    logger.info(f"generate_screen_design | project_id={request.project_id}")
    request.target_artifact_type = ArtifactType.SCREEN_DESIGN
    request.source_document_type = request.source_document_type or (
        DocumentType.REQUIREMENT_SPEC
    )

    await _validate_source_documents(
        request=request,
        document_service=document_service,
        required_source_type=DocumentType.REQUIREMENT_SPEC,
    )
    input_response = await _normalize_generation_input(request, input_orchestrator)
    if not input_response.success:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="GENERATION_INPUT_NORMALIZATION_FAILED",
            message=input_response.error or "generation input normalization failed",
            detail={"errors": input_response.validation_errors},
        )
    response = await generation_service.generate_artifact(
        request,
        artifact_service=artifact_service,
        retrieval_service=retrieval_service,
        template_service=template_service,
    )
    return await _format_generation_response(response, output_orchestrator)


async def _normalize_generation_input(
    request: GenerationRequest,
    input_orchestrator: InputOrchestrator,
) -> InputAgentResponse:
    return await input_orchestrator.normalize(
        InputAgentRequest(
            project_id=request.project_id,
            permission_scope=request.permission_scope,
            input_type=InputType.ARTIFACT_REQUEST,
            raw_payload=request.model_dump(mode="json"),
            context={
                "target_artifact_type": request.target_artifact_type.value,
                "source_document_ids": request.source_document_ids,
                "query": request.query,
            },
        )
    )


async def _validate_source_documents(
    *,
    request: GenerationRequest,
    document_service: DocumentService,
    required_source_type: DocumentType | None = None,
) -> None:
    if not request.source_document_ids:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="SOURCE_DOCUMENT_REQUIRED",
            message="source document is required",
            detail={
                "project_id": request.project_id,
                "target_artifact_type": request.target_artifact_type.value,
            },
        )

    missing_document_ids: list[str] = []
    invalid_type_documents: list[dict] = []
    for document_id in request.source_document_ids:
        document = await document_service.get_document(
            project_id=request.project_id,
            document_id=document_id,
        )
        if document is None:
            missing_document_ids.append(document_id)
            continue

        if required_source_type is not None and (
            document.document_type != required_source_type
        ):
            invalid_type_documents.append(
                {
                    "document_id": document.document_id,
                    "document_type": document.document_type.value,
                    "required_document_type": required_source_type.value,
                }
            )

    if missing_document_ids:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="SOURCE_DOCUMENT_NOT_FOUND",
            message="source document not found",
            detail={
                "project_id": request.project_id,
                "missing_document_ids": missing_document_ids,
            },
        )

    if invalid_type_documents:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="INVALID_SOURCE_DOCUMENT_TYPE",
            message=(
                f"{request.target_artifact_type.value} must be generated from "
                f"{required_source_type.value}"
            ),
            detail={"documents": invalid_type_documents},
        )


async def _format_generation_response(
    response: GenerationResponse,
    output_orchestrator: OutputOrchestrator,
) -> GenerationResponse:
    if not response.success:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="GENERATION_FAILED",
            message=response.message,
            detail=response.result,
        )

    output_response = await output_orchestrator.format(
        OutputAgentRequest(
            project_id=response.project_id,
            response_type=OutputResponseType.API_RESPONSE,
            result_json={
                "success": response.success,
                "message": response.message,
                "result": response.result,
            },
            message=response.message,
            errors=[] if response.success else [response.message],
        )
    )
    if isinstance(response.result, dict):
        response.result = {
            **response.result,
            "display": output_response.display_payload,
        }

    return response
