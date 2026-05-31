# EN: Generation API routes delegate artifact generation requests to orchestrators.
# KO: 산출물 생성 API 라우터이며 요청 처리를 오케스트레이터에 위임합니다.

from fastapi import APIRouter, Depends

from app.core.logger import get_logger
from app.dependencies import (
    get_artifact_service,
    get_generation_service,
    get_retrieval_service,
)
from app.rag.retrieval import RetrievalService
from app.schemas.request import GenerationRequest
from app.schemas.response import GenerationResponse
from app.services.artifact_service import ArtifactService
from app.services.generation_service import GenerationService

logger = get_logger(__name__)
router = APIRouter()


@router.post("/requirement", response_model=GenerationResponse)
async def generate_requirement(
    request: GenerationRequest,
    generation_service: GenerationService = Depends(get_generation_service),
    artifact_service: ArtifactService = Depends(get_artifact_service),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
) -> GenerationResponse:
    """Generate a requirement artifact through the PM agent orchestrator."""
    logger.info(f"generate_requirement | project_id={request.project_id}")

    return await generation_service.generate_requirement(
        request,
        artifact_service=artifact_service,
        retrieval_service=retrieval_service,
    )


@router.post("/action-items", response_model=GenerationResponse)
async def generate_action_items(request: GenerationRequest) -> GenerationResponse:
    """Extract action items from meeting context."""
    logger.info(f"generate_action_items | project_id={request.project_id}")

    return GenerationResponse(
        project_id=request.project_id,
        result={"mock": "Action item extraction result"},
    )
