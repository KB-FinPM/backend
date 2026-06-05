# EN: Business service for project-scoped chat interactions.

from app.orchestrator.chat_orchestrator import ChatOrchestrator
from app.schemas.chat import ChatMessageRequest, ChatResponse


class ChatService:
    """Keeps chat API routes stable while the chat orchestrator evolves."""

    def __init__(self, orchestrator: ChatOrchestrator) -> None:
        self.orchestrator = orchestrator

    async def handle_message(self, request: ChatMessageRequest) -> ChatResponse:
        return await self.orchestrator.handle_message(request)
