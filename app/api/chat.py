# EN: Chat API routes for conversational PM workflows.

from fastapi import APIRouter, Body, Depends, status

from app.dependencies import get_chat_service
from app.schemas.chat import ChatMessageRequest, ChatResponse
from app.schemas.response import ErrorResponse
from app.services.chat_service import ChatService

router = APIRouter()

CHAT_ERROR_RESPONSES = {
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
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    """Handle one chat message and optionally prepare or execute PM actions."""
    return await chat_service.handle_message(request)
