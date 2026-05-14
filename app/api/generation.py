from fastapi import APIRouter
from app.schemas.request import GenerationRequest
from app.schemas.response import GenerationResponse
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/requirement", response_model=GenerationResponse)
async def generate_requirement(request: GenerationRequest):
    """
    요구사항 정의서 생성.
    TODO: GenerationOrchestrator 연동
    """
    logger.info(f"generate_requirement | project_id={request.project_id}")

    # TODO: orchestrator.generate_requirement(request) 호출

    return GenerationResponse(
        project_id=request.project_id,
        result={"mock": "요구사항 생성 결과 (Mock)"},
    )


@router.post("/action-items", response_model=GenerationResponse)
async def generate_action_items(request: GenerationRequest):
    """
    회의록 기반 Action Item 추출.
    TODO: ActionItemOrchestrator 연동
    """
    logger.info(f"generate_action_items | project_id={request.project_id}")

    return GenerationResponse(
        project_id=request.project_id,
        result={"mock": "Action Item 추출 결과 (Mock)"},
    )
