# EN: Schedule-management API routes.

from fastapi import APIRouter, Body, Depends, status

from app.core.auth import CurrentUser, assert_project_access
from app.core.exceptions import ApiError
from app.core.logger import get_logger
from app.dependencies import (
    get_current_user,
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
from app.schemas.response import ErrorResponse, ScheduleTodoResponse
from app.services.schedule_service import ScheduleService

logger = get_logger(__name__)
router = APIRouter()

SCHEDULE_ERROR_RESPONSES = {
    status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}

ACTION_ITEM_EXAMPLE = {
    "summary": "Extract action items from weekly meeting notes",
    "value": {
        "project_id": "PRJ-001",
        "meeting_notes": (
            "2026-06-04 weekly meeting: Kim owns login scope review by "
            "2026-06-07. Lee will confirm API exception policy."
        ),
        "source_document_ids": ["DOC-MEETING-001"],
        "user_id": "USER-001",
        "permission_scope": ["project:read"],
    },
}


@router.post(
    "/todos",
    response_model=ScheduleTodoResponse,
    responses=SCHEDULE_ERROR_RESPONSES,
)
async def extract_schedule_todos(
    request: ScheduleTodoRequest = Body(
        ...,
        openapi_examples={"weekly_meeting_action_items": ACTION_ITEM_EXAMPLE},
    ),
    schedule_service: ScheduleService = Depends(get_schedule_service),
    input_orchestrator: InputOrchestrator = Depends(get_input_orchestrator),
    output_orchestrator: OutputOrchestrator = Depends(get_output_orchestrator),
    current_user: CurrentUser = Depends(get_current_user),
) -> ScheduleTodoResponse:
    """Extract action items from meeting notes."""
    logger.info(f"extract_schedule_todos | project_id={request.project_id}")
    permissions = assert_project_access(
        current_user,
        request.project_id,
        "schedule:write",
    )
    request.user_id = current_user.user_id
    request.permission_scope = permissions.scopes

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
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="SCHEDULE_INPUT_NORMALIZATION_FAILED",
            message=input_response.error or "schedule input normalization failed",
            detail={"errors": input_response.validation_errors},
        )

    response = await schedule_service.extract_todos(
        request,
        structured_context=input_response.structured_context,
    )
    return await _format_schedule_response(response, output_orchestrator)


@router.post(
    "/action-items",
    response_model=ScheduleTodoResponse,
    responses=SCHEDULE_ERROR_RESPONSES,
)
async def extract_action_items(
    request: ScheduleTodoRequest = Body(
        ...,
        openapi_examples={"weekly_meeting_action_items": ACTION_ITEM_EXAMPLE},
    ),
    schedule_service: ScheduleService = Depends(get_schedule_service),
    input_orchestrator: InputOrchestrator = Depends(get_input_orchestrator),
    output_orchestrator: OutputOrchestrator = Depends(get_output_orchestrator),
    current_user: CurrentUser = Depends(get_current_user),
) -> ScheduleTodoResponse:
    """Extract action items from weekly meeting notes."""
    return await extract_schedule_todos(
        request=request,
        schedule_service=schedule_service,
        input_orchestrator=input_orchestrator,
        output_orchestrator=output_orchestrator,
        current_user=current_user,
    )


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
