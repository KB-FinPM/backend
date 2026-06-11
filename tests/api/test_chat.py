# EN: Tests for chat API routing behavior.

from fastapi.testclient import TestClient

from app.dependencies import get_chat_service
from app.schemas.chat import ChatMessageRequest, ChatResponse, ChatState


class StubChatService:
    def __init__(self) -> None:
        self.received_request: ChatMessageRequest | None = None

    async def handle_message(self, request: ChatMessageRequest) -> ChatResponse:
        self.received_request = request
        return ChatResponse(
            conversation_id=request.conversation_id or "CONV-001",
            message_id="MSG-ASSISTANT-001",
            message="선택된 문서를 기준으로 WBS 문서를 생성해드릴까요?",
            state=ChatState.WAITING_CONFIRMATION,
        )


def test_chat_messages_route_delegates_to_chat_service(client: TestClient) -> None:
    service = StubChatService()
    client.app.dependency_overrides[get_chat_service] = lambda: service

    try:
        response = client.post(
            "/api/chat/messages",
            json={
                "project_id": "PRJ-001",
                "message": "이 요구사항으로 WBS 만들어줘",
                "context": {"selected_document_ids": ["DOC-REQ-001"]},
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == "CONV-001"
    assert body["state"] == "WAITING_CONFIRMATION"
    assert service.received_request is not None
    assert service.received_request.context["selected_document_ids"] == [
        "DOC-REQ-001"
    ]
