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
    get_project_service,
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
from app.services.project_service import ProjectService
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
        "author": "작성자",
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
        "start_date": "2024-01-10",
        "project_period": "6개월",
        "query": "Create a WBS from the requirement specification.",
        "author": "작성자",
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
        "author": "작성자",
        "permission_scope": ["project:read"],
    },
}

UNITTEST_EXAMPLE = {
    "summary": "Build unit test cases from requirement specification",
    "value": {
        "project_id": "PRJ-TEST-001",
        "project_name": "테스트 구축 프로젝트",
        "author": "김국민",
        "source_document_ids": ["DOC-ADA194C012AF"],
        "source_document_type": "REQUIREMENT_SPEC",
        "target_artifact_type": "UNITTEST_SPEC",
        "query": "단위테스트케이스를 생성해줘",
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
    project_service: ProjectService = Depends(get_project_service),
    input_orchestrator: InputOrchestrator = Depends(get_input_orchestrator),
    output_orchestrator: OutputOrchestrator = Depends(get_output_orchestrator),
) -> GenerationResponse:
    """Generate a requirement artifact through the PM agent orchestrator."""
    logger.info(f"generate_requirement | project_id={request.project_id}")

    return await _generate_artifact_response(
        request=request,
        generation_service=generation_service,
        artifact_service=artifact_service,
        document_service=document_service,
        retrieval_service=retrieval_service,
        template_service=template_service,
        project_service=project_service,
        input_orchestrator=input_orchestrator,
        output_orchestrator=output_orchestrator,
    )


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
    project_service: ProjectService = Depends(get_project_service),
    input_orchestrator: InputOrchestrator = Depends(get_input_orchestrator),
    output_orchestrator: OutputOrchestrator = Depends(get_output_orchestrator),
) -> GenerationResponse:
    """Generate a WBS artifact through the PM agent orchestrator."""
    logger.info(f"generate_wbs | project_id={request.project_id}")
    request.target_artifact_type = ArtifactType.WBS
    request.source_document_type = request.source_document_type or (
        DocumentType.REQUIREMENT_SPEC
    )

    return await _generate_artifact_response(
        request=request,
        generation_service=generation_service,
        artifact_service=artifact_service,
        document_service=document_service,
        retrieval_service=retrieval_service,
        template_service=template_service,
        project_service=project_service,
        input_orchestrator=input_orchestrator,
        output_orchestrator=output_orchestrator,
    )


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
    project_service: ProjectService = Depends(get_project_service),
    input_orchestrator: InputOrchestrator = Depends(get_input_orchestrator),
    output_orchestrator: OutputOrchestrator = Depends(get_output_orchestrator),
) -> GenerationResponse:
    """Generate a screen design artifact through the PM agent orchestrator."""
    logger.info(f"generate_screen_design | project_id={request.project_id}")
    request.target_artifact_type = ArtifactType.SCREEN_DESIGN
    request.source_document_type = request.source_document_type or (
        DocumentType.REQUIREMENT_SPEC
    )

    return await _generate_artifact_response(
        request=request,
        generation_service=generation_service,
        artifact_service=artifact_service,
        document_service=document_service,
        retrieval_service=retrieval_service,
        template_service=template_service,
        project_service=project_service,
        input_orchestrator=input_orchestrator,
        output_orchestrator=output_orchestrator,
    )


@router.post(
    "/unittest",
    response_model=GenerationResponse,
    responses=GENERATION_ERROR_RESPONSES,
)
async def generate_unittest(
    request: GenerationRequest = Body(
        ...,
        openapi_examples={"unittest": UNITTEST_EXAMPLE},
    ),
    generation_service: GenerationService = Depends(get_generation_service),
    artifact_service: ArtifactService = Depends(get_artifact_service),
    document_service: DocumentService = Depends(get_document_service),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    template_service: TemplateService = Depends(get_template_service),
    project_service: ProjectService = Depends(get_project_service),
    input_orchestrator: InputOrchestrator = Depends(get_input_orchestrator),
    output_orchestrator: OutputOrchestrator = Depends(get_output_orchestrator),
) -> GenerationResponse:
    """Generate a unit test case artifact through the PM agent orchestrator."""
    logger.info(f"generate_unittest | project_id={request.project_id}")
    request.target_artifact_type = ArtifactType.UNITTEST_SPEC
    request.source_document_type = request.source_document_type or (
        DocumentType.REQUIREMENT_SPEC
    )

    return await _generate_artifact_response(
        request=request,
        generation_service=generation_service,
        artifact_service=artifact_service,
        document_service=document_service,
        retrieval_service=retrieval_service,
        template_service=template_service,
        project_service=project_service,
        input_orchestrator=input_orchestrator,
        output_orchestrator=output_orchestrator,
    )


async def _generate_artifact_response(
    *,
    request: GenerationRequest,
    generation_service: GenerationService,
    artifact_service: ArtifactService,
    document_service: DocumentService,
    retrieval_service: RetrievalService,
    template_service: TemplateService,
    project_service: ProjectService,
    input_orchestrator: InputOrchestrator,
    output_orchestrator: OutputOrchestrator,
) -> GenerationResponse:
    await _hydrate_project_metadata(request, project_service)
    await _validate_source_documents(
        request=request,
        generation_service=generation_service,
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
        document_service=document_service,
    )
    return await _format_generation_response(response, output_orchestrator)


async def _hydrate_project_metadata(
    request: GenerationRequest,
    project_service: ProjectService,
) -> None:
    if request.project_name and request.start_date:
        return
    project = await project_service.get_project(request.project_id)
    if project is None:
        return
    if not request.project_name:
        request.project_name = project.project_name
    if not request.start_date and project.start_date is not None:
        request.start_date = project.start_date.isoformat()


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
                "project_id": request.project_id,
                "project_name": request.project_name,
                "source_document_type": (
                    request.source_document_type.value
                    if request.source_document_type
                    else None
                ),
                "target_artifact_type": request.target_artifact_type.value,
                "source_document_ids": request.source_document_ids,
                "query": request.query,
                "start_date": request.start_date,
                "project_period": request.project_period,
            },
        )
    )


async def _validate_source_documents(
    *,
    request: GenerationRequest,
    generation_service: GenerationService,
    document_service: DocumentService,
) -> None:
    result = await generation_service.validate_source_documents(
        request,
        document_service=document_service,
    )
    if result.success:
        return

    if result.error_code == "SOURCE_DOCUMENT_REQUIRED":
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code=result.error_code,
            message=result.message,
            detail=result.detail,
        )

    if result.error_code == "SOURCE_DOCUMENT_NOT_FOUND":
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code=result.error_code,
            message=result.message,
            detail=result.detail,
        )

    if result.error_code == "INVALID_SOURCE_DOCUMENT_TYPE":
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code=result.error_code,
            message=result.message,
            detail=result.detail,
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
        exported_document = response.result.get("exported_document")
        if isinstance(exported_document, dict):
            response.document_id = exported_document.get("document_id")
            document_type = exported_document.get("document_type")
            response.document_type = (
                document_type.value if hasattr(document_type, "value") else document_type
            )
        response.result = {
            **response.result,
            "display": output_response.display_payload,
        }

    return response
