from fastapi import APIRouter

from app.core.logger import get_logger
from app.orchestrator.generation_orchestrator import generation_orchestrator
from app.schemas.request import GenerationRequest
from app.schemas.response import GenerationResponse

logger = get_logger(__name__)
router = APIRouter()


@router.post("/requirement", response_model=GenerationResponse)
async def generate_requirement(request: GenerationRequest) -> GenerationResponse:
    """Generate a requirement artifact through the PM agent orchestrator."""
    logger.info(f"generate_requirement | project_id={request.project_id}")

    return await generation_orchestrator.generate_requirement(request)


@router.post("/action-items", response_model=GenerationResponse)
async def generate_action_items(request: GenerationRequest) -> GenerationResponse:
    """Extract action items from meeting context."""
    logger.info(f"generate_action_items | project_id={request.project_id}")

    return GenerationResponse(
        project_id=request.project_id,
        result={"mock": "Action item extraction result"},
    )
