# EN: Schedule-management API routes.

from fastapi import APIRouter, Depends

from app.core.logger import get_logger
from app.dependencies import (
    get_input_orchestrator,
    get_output_orchestrator,
    get_schedule_service,
)
from app.orchestrator.input_orchestrator import InputOrchestrator
from app.orchestrator.output_orchestrator import OutputOrchestrator
from app.schemas.io_agent import (
    InputAgentRequest,
    InputType,
    OutputAgentRequest,
    OutputResponseType,
)
from app.schemas.request import ScheduleTodoRequest
from app.schemas.response import ScheduleTodoResponse
from app.services.schedule_service import ScheduleService

logger = get_logger(__name__)
router = APIRouter()


@router.post("/todos", response_model=ScheduleTodoResponse)
async def extract_schedule_todos(
    request: ScheduleTodoRequest,
    schedule_service: ScheduleService = Depends(get_schedule_service),
    input_orchestrator: InputOrchestrator = Depends(get_input_orchestrator),
    output_orchestrator: OutputOrchestrator = Depends(get_output_orchestrator),
) -> ScheduleTodoResponse:
    """Extract lightweight todo items from meeting notes."""
    logger.info(f"extract_schedule_todos | project_id={request.project_id}")

    input_response = await input_orchestrator.normalize(
        InputAgentRequest(
            project_id=request.project_id,
            user_id=request.user_id,
            permission_scope=request.permission_scope,
            input_type=InputType.MEETING_NOTES,
            raw_payload=request.model_dump(mode="json"),
            context={
                "source_document_ids": request.source_document_ids,
            },
        )
    )
    if not input_response.success:
        return ScheduleTodoResponse(
            success=False,
            message=input_response.error or "input normalization failed",
            project_id=request.project_id,
            result={"errors": input_response.validation_errors},
        )

    response = await schedule_service.extract_todos(
        request,
        structured_context=input_response.structured_context,
    )
    return await _format_schedule_response(response, output_orchestrator)


async def _format_schedule_response(
    response: ScheduleTodoResponse,
    output_orchestrator: OutputOrchestrator,
) -> ScheduleTodoResponse:
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
    response.display = output_response.display_payload
    return response
