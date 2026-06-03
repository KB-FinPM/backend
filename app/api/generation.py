# EN: Generation API routes delegate artifact generation requests to orchestrators.
# KO: 산출물 생성 API 라우터이며 요청 처리를 오케스트레이터에 위임합니다.

from fastapi import APIRouter, Depends

from app.core.logger import get_logger
from app.dependencies import (
    get_artifact_service,
    get_generation_service,
    get_input_orchestrator,
    get_output_orchestrator,
    get_retrieval_service,
    get_template_service,
)
from app.orchestrator.input_orchestrator import InputOrchestrator
from app.orchestrator.output_orchestrator import OutputOrchestrator
from app.rag.retrieval import RetrievalService
from app.schemas.artifact import ArtifactType
from app.schemas.io_agent import (
    InputAgentRequest,
    InputAgentResponse,
    InputType,
    OutputAgentRequest,
    OutputResponseType,
)
from app.schemas.request import GenerationRequest
from app.schemas.response import GenerationResponse
from app.services.artifact_service import ArtifactService
from app.services.generation_service import GenerationService
from app.services.template_service import TemplateService

logger = get_logger(__name__)
router = APIRouter()


@router.post("/requirement", response_model=GenerationResponse)
async def generate_requirement(
    request: GenerationRequest,
    generation_service: GenerationService = Depends(get_generation_service),
    artifact_service: ArtifactService = Depends(get_artifact_service),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    template_service: TemplateService = Depends(get_template_service),
    input_orchestrator: InputOrchestrator = Depends(get_input_orchestrator),
    output_orchestrator: OutputOrchestrator = Depends(get_output_orchestrator),
) -> GenerationResponse:
    """Generate a requirement artifact through the PM agent orchestrator."""
    logger.info(f"generate_requirement | project_id={request.project_id}")

    input_response = await _normalize_generation_input(request, input_orchestrator)
    if not input_response.success:
        return GenerationResponse(
            success=False,
            message=input_response.error or "input normalization failed",
            project_id=request.project_id,
            result={"errors": input_response.validation_errors},
        )
    response = await generation_service.generate_artifact(
        request,
        artifact_service=artifact_service,
        retrieval_service=retrieval_service,
        template_service=template_service,
    )
    return await _format_generation_response(response, output_orchestrator)


@router.post("/wbs", response_model=GenerationResponse)
async def generate_wbs(
    request: GenerationRequest,
    generation_service: GenerationService = Depends(get_generation_service),
    artifact_service: ArtifactService = Depends(get_artifact_service),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    template_service: TemplateService = Depends(get_template_service),
    input_orchestrator: InputOrchestrator = Depends(get_input_orchestrator),
    output_orchestrator: OutputOrchestrator = Depends(get_output_orchestrator),
) -> GenerationResponse:
    """Generate a WBS artifact through the PM agent orchestrator."""
    logger.info(f"generate_wbs | project_id={request.project_id}")
    request.target_artifact_type = ArtifactType.WBS

    input_response = await _normalize_generation_input(request, input_orchestrator)
    if not input_response.success:
        return GenerationResponse(
            success=False,
            message=input_response.error or "input normalization failed",
            project_id=request.project_id,
            result={"errors": input_response.validation_errors},
        )
    response = await generation_service.generate_artifact(
        request,
        artifact_service=artifact_service,
        retrieval_service=retrieval_service,
        template_service=template_service,
    )
    return await _format_generation_response(response, output_orchestrator)


@router.post("/screen-design", response_model=GenerationResponse)
async def generate_screen_design(
    request: GenerationRequest,
    generation_service: GenerationService = Depends(get_generation_service),
    artifact_service: ArtifactService = Depends(get_artifact_service),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    template_service: TemplateService = Depends(get_template_service),
    input_orchestrator: InputOrchestrator = Depends(get_input_orchestrator),
    output_orchestrator: OutputOrchestrator = Depends(get_output_orchestrator),
) -> GenerationResponse:
    """Generate a screen design artifact through the PM agent orchestrator."""
    logger.info(f"generate_screen_design | project_id={request.project_id}")
    request.target_artifact_type = ArtifactType.SCREEN_DESIGN

    input_response = await _normalize_generation_input(request, input_orchestrator)
    if not input_response.success:
        return GenerationResponse(
            success=False,
            message=input_response.error or "input normalization failed",
            project_id=request.project_id,
            result={"errors": input_response.validation_errors},
        )
    response = await generation_service.generate_artifact(
        request,
        artifact_service=artifact_service,
        retrieval_service=retrieval_service,
        template_service=template_service,
    )
    return await _format_generation_response(response, output_orchestrator)


@router.post("/action-items", response_model=GenerationResponse)
async def generate_action_items(request: GenerationRequest) -> GenerationResponse:
    """Extract action items from meeting context."""
    logger.info(f"generate_action_items | project_id={request.project_id}")

    return GenerationResponse(
        project_id=request.project_id,
        result={"mock": "Action item extraction result"},
    )


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


async def _format_generation_response(
    response: GenerationResponse,
    output_orchestrator: OutputOrchestrator,
) -> GenerationResponse:
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
