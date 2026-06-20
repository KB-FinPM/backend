# EN: Chat API routes for conversational PM workflows.

from fastapi import APIRouter, Body, Depends, Query, status

from app.core.auth import CurrentUser, assert_project_access
from app.core.exceptions import ApiError
from app.dependencies import (
    get_current_user,
    get_chat_service,
    get_conversation_repository,
    get_output_orchestrator,
)
from app.orchestrator.output_orchestrator import OutputOrchestrator
from app.repositories.conversation_repository import ConversationRepository
from app.schemas.chat import (
    ChatActionMetadata,
    ChatActionStatus,
    ChatActionStatusResponse,
    ChatMessageRequest,
    ChatResponse,
    ChatState,
)
from app.schemas.io_agent import OutputAgentRequest, OutputResponseType
from app.schemas.response import ErrorResponse
from app.services.chat_service import ChatService

router = APIRouter()

CHAT_ERROR_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}


@router.post(
    "/messages",
    response_model=ChatResponse,
    responses=CHAT_ERROR_RESPONSES,
)
async def create_chat_message(
    request: ChatMessageRequest = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    """Handle one chat message and optionally prepare or execute PM actions."""
    permissions = assert_project_access(current_user, request.project_id, "chat:write")
    request.user_id = current_user.user_id
    request.permission_scope = permissions.scopes
    return await chat_service.handle_message(request)


@router.get(
    "/actions/{action_id}",
    response_model=ChatActionStatusResponse,
    responses=CHAT_ERROR_RESPONSES,
)
async def get_chat_action_status(
    action_id: str,
    project_id: str = Query(...),
    current_user: CurrentUser = Depends(get_current_user),
    conversation_repository: ConversationRepository = Depends(
        get_conversation_repository
    ),
    output_orchestrator: OutputOrchestrator = Depends(get_output_orchestrator),
) -> ChatActionStatusResponse:
    assert_project_access(current_user, project_id, "project:read")
    action = await conversation_repository.get_action(
        project_id=project_id,
        action_id=action_id,
    )
    if action is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="ACTION_NOT_FOUND",
            message="action not found",
            detail={"project_id": project_id, "action_id": action_id},
        )

    return await _build_action_status_response(action, output_orchestrator)


async def _build_action_status_response(
    action: ChatActionMetadata,
    output_orchestrator: OutputOrchestrator,
) -> ChatActionStatusResponse:
    if action.status == ChatActionStatus.EXECUTED:
        generation_result = action.result_json or {}
        result = generation_result.get("result")
        if not isinstance(result, dict):
            result = {}
        output_response = await output_orchestrator.format(
            OutputAgentRequest(
                project_id=action.project_id,
                response_type=OutputResponseType.CHAT_RESPONSE,
                result_json={
                    "event": "ACTION_COMPLETED",
                    "result": result,
                },
                message=generation_result.get("message") or "artifact generated",
            )
        )
        payload = output_response.display_payload
        return ChatActionStatusResponse(
            message=payload.get("message", "artifact generated"),
            project_id=action.project_id,
            action_id=action.action_id,
            conversation_id=action.conversation_id,
            status=action.status,
            state=ChatState(payload.get("state", ChatState.COMPLETED.value)),
            pending_action=action,
            result=payload.get("result") or {
                "action_id": action.action_id,
                "job_id": action.action_id,
                "generation": generation_result,
            },
            download_files=payload.get("download_files") or [],
        )

    if action.status == ChatActionStatus.FAILED:
        generation_result = action.result_json or {}
        error = generation_result.get("message") or generation_result.get("error")
        result = generation_result.get("result")
        if isinstance(result, dict):
            error = error or result.get("error")
        output_response = await output_orchestrator.format(
            OutputAgentRequest(
                project_id=action.project_id,
                response_type=OutputResponseType.CHAT_RESPONSE,
                result_json={
                    "event": "ACTION_FAILED",
                    "error": error or "generation failed",
                    "result": generation_result,
                },
                message="generation failed",
            )
        )
        payload = output_response.display_payload
        return ChatActionStatusResponse(
            message=payload.get("message", "generation failed"),
            project_id=action.project_id,
            action_id=action.action_id,
            conversation_id=action.conversation_id,
            status=action.status,
            state=ChatState(payload.get("state", ChatState.FAILED.value)),
            pending_action=action,
            result=payload.get("result") or {"error": error},
            download_files=[],
        )

    state = (
        ChatState.IDLE
        if action.status == ChatActionStatus.CANCELLED
        else ChatState.EXECUTING_ACTION
    )
    return ChatActionStatusResponse(
        message="generation is running"
        if action.status == ChatActionStatus.EXECUTING
        else "action is not complete",
        project_id=action.project_id,
        action_id=action.action_id,
        conversation_id=action.conversation_id,
        status=action.status,
        state=state,
        pending_action=action,
        result={
            "action_id": action.action_id,
            "job_id": action.action_id,
            "status": action.status.value,
            **(
                action.result_json
                if isinstance(action.result_json, dict)
                else {}
            ),
        },
        download_files=[],
    )
