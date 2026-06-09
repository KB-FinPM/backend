# EN: Tests for chat orchestration over pending PM actions.

import pytest

from app.orchestrator.chat_orchestrator import ChatOrchestrator
from app.schemas.artifact import DocumentMetadata, DocumentType
from app.schemas.chat import ChatMessageRequest
from app.schemas.response import GenerationResponse
from app.services.generation_service import GenerationSourceValidationResult


class StubConversationRepository:
    def __init__(self) -> None:
        self.conversations = {}
        self.actions = {}
        self.messages = []

    async def create_conversation(self, **kwargs):
        from app.schemas.chat import ConversationMetadata

        conversation = ConversationMetadata(**kwargs)
        self.conversations[conversation.conversation_id] = conversation
        return conversation

    async def get_conversation(self, *, project_id, conversation_id):
        conversation = self.conversations.get(conversation_id)
        if conversation and conversation.project_id == project_id:
            return conversation
        return None

    async def add_message(self, **kwargs):
        from app.schemas.chat import ChatMessageMetadata

        message = ChatMessageMetadata(**kwargs)
        self.messages.append(message)
        return message

    async def create_action(self, **kwargs):
        from app.schemas.chat import ChatActionMetadata, ChatActionStatus

        kwargs.setdefault("status", ChatActionStatus.WAITING_CONFIRMATION)
        action = ChatActionMetadata(**kwargs)
        self.actions[action.action_id] = action
        return action

    async def get_latest_waiting_action(self, *, project_id, conversation_id):
        from app.schemas.chat import ChatActionStatus

        for action in reversed(list(self.actions.values())):
            if (
                action.project_id == project_id
                and action.conversation_id == conversation_id
                and action.status == ChatActionStatus.WAITING_CONFIRMATION
            ):
                return action
        return None

    async def get_action(self, *, project_id, action_id):
        action = self.actions.get(action_id)
        if action and action.project_id == project_id:
            return action
        return None

    async def update_action_status(
        self,
        *,
        project_id,
        action_id,
        status,
        result_json=None,
    ):
        action = self.actions[action_id]
        updated = action.model_copy(
            update={
                "status": status,
                "result_json": result_json if result_json is not None else {},
            }
        )
        self.actions[action_id] = updated
        return updated


class StubDocumentService:
    async def get_document(self, *, project_id, document_id):
        return DocumentMetadata(
            document_id=document_id,
            project_id=project_id,
            document_type=DocumentType.REQUIREMENT_SPEC,
            file_name="requirement.txt",
            storage_path="s3://bucket/requirement.txt",
        )


class StubGenerationService:
    def __init__(self) -> None:
        self.received_request = None

    async def generate_artifact(
        self,
        request,
        *,
        artifact_service=None,
        retrieval_service=None,
        template_service=None,
    ):
        self.received_request = request
        return GenerationResponse(
            project_id=request.project_id,
            message="artifact generated",
            result={
                "artifact": {
                    "artifact_id": "ART-001",
                    "project_id": request.project_id,
                    "artifact_type": request.target_artifact_type.value,
                    "name": request.target_artifact_type.value,
                    "version": 1,
                    "source_document_ids": request.source_document_ids,
                    "result_json": {},
                    "status": "CREATED",
                },
                "generated": {"artifact_type": request.target_artifact_type.value},
            },
        )

    async def validate_source_documents(
        self,
        request,
        *,
        document_service,
        required_source_type=None,
    ):
        return GenerationSourceValidationResult(
            project_id=request.project_id,
            target_artifact_type=request.target_artifact_type,
            required_source_type=required_source_type,
        )


class StubScheduleService:
    pass


@pytest.mark.anyio
async def test_chat_orchestrator_prepares_and_confirms_generation_action() -> None:
    repository = StubConversationRepository()
    generation_service = StubGenerationService()
    orchestrator = ChatOrchestrator(
        conversation_repository=repository,
        generation_service=generation_service,
        schedule_service=StubScheduleService(),
        document_service=StubDocumentService(),
        artifact_service=object(),
        retrieval_service=object(),
        template_service=object(),
    )

    first_response = await orchestrator.handle_message(
        ChatMessageRequest(
            project_id="PRJ-001",
            user_id="USER-001",
            message="이 요구사항으로 WBS 만들어줘",
            context={"selected_document_ids": ["DOC-REQ-001"]},
        )
    )
    second_response = await orchestrator.handle_message(
        ChatMessageRequest(
            project_id="PRJ-001",
            conversation_id=first_response.conversation_id,
            user_id="USER-001",
            message="생성해",
        )
    )

    assert first_response.state == "WAITING_CONFIRMATION"
    assert second_response.state == "COMPLETED"
    assert generation_service.received_request is not None
    assert generation_service.received_request.target_artifact_type == "WBS"
