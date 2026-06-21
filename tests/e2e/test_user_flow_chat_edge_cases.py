from __future__ import annotations

from typing import Any

import pytest

from app.core.auth import DEFAULT_MVP_SCOPES
from app.orchestrator.chat_orchestrator import ChatOrchestrator
from app.schemas.artifact import ArtifactType, DocumentMetadata, DocumentType
from app.schemas.chat import (
    ChatActionCommand,
    ChatActionMetadata,
    ChatActionStatus,
    ChatActionType,
    ChatCommandType,
    ChatMessageMetadata,
    ChatMessageRequest,
    ChatRole,
    ChatState,
    ConversationMetadata,
)
from app.schemas.io_agent import InputAgentResponse, NormalizedRequestType
from app.schemas.response import GenerationResponse
from app.services.generation_service import GenerationSourceValidationResult


PROJECT_ID = "PRJ-CHAT-EDGE-001"


class InMemoryConversationRepository:
    def __init__(self) -> None:
        self.conversations: dict[str, ConversationMetadata] = {}
        self.actions: dict[str, ChatActionMetadata] = {}
        self.messages: list[ChatMessageMetadata] = []

    async def create_conversation(self, **kwargs: Any) -> ConversationMetadata:
        conversation = ConversationMetadata(**kwargs)
        self.conversations[conversation.conversation_id] = conversation
        return conversation

    async def get_conversation(
        self,
        *,
        project_id: str,
        conversation_id: str,
    ) -> ConversationMetadata | None:
        conversation = self.conversations.get(conversation_id)
        if conversation and conversation.project_id == project_id:
            return conversation
        return None

    async def add_message(self, **kwargs: Any) -> ChatMessageMetadata:
        message = ChatMessageMetadata(**kwargs)
        self.messages.append(message)
        return message

    async def create_action(self, **kwargs: Any) -> ChatActionMetadata:
        kwargs.setdefault("status", ChatActionStatus.WAITING_CONFIRMATION)
        action = ChatActionMetadata(**kwargs)
        self.actions[action.action_id] = action
        return action

    async def get_latest_waiting_action(
        self,
        *,
        project_id: str,
        conversation_id: str,
    ) -> ChatActionMetadata | None:
        for action in reversed(list(self.actions.values())):
            if (
                action.project_id == project_id
                and action.conversation_id == conversation_id
                and action.status == ChatActionStatus.WAITING_CONFIRMATION
            ):
                return action
        return None

    async def get_action(
        self,
        *,
        project_id: str,
        action_id: str,
    ) -> ChatActionMetadata | None:
        action = self.actions.get(action_id)
        if action and action.project_id == project_id:
            return action
        return None

    async def update_action_status(
        self,
        *,
        project_id: str,
        action_id: str,
        status: ChatActionStatus,
        result_json: dict[str, Any] | None = None,
    ) -> ChatActionMetadata:
        action = self.actions[action_id]
        updated = action.model_copy(
            update={
                "status": status,
                "result_json": result_json if result_json is not None else {},
            }
        )
        self.actions[action_id] = updated
        return updated


class CommandAwareInputNormalizer:
    def __init__(self, initial_context: dict[str, Any]) -> None:
        self.initial_context = initial_context

    async def normalize(self, request):
        action = (request.raw_payload or {}).get("action") or {}
        action_type = action.get("type")
        if action_type == ChatCommandType.CONFIRM_PENDING_ACTION.value:
            structured_context = {
                "intent": "CONFIRM_PENDING_ACTION",
                "action_id": action.get("action_id"),
            }
        elif action_type == ChatCommandType.CANCEL_PENDING_ACTION.value:
            structured_context = {
                "intent": "CANCEL_PENDING_ACTION",
                "action_id": action.get("action_id"),
            }
        else:
            structured_context = self.initial_context

        return InputAgentResponse(
            agent_name="CommandAwareInputNormalizer",
            normalized_request_type=NormalizedRequestType.CHAT_MESSAGE,
            structured_context=structured_context,
        )


class ChatDocumentService:
    async def get_document(self, *, project_id: str, document_id: str):
        return DocumentMetadata(
            document_id=document_id,
            project_id=project_id,
            document_type=DocumentType.REQUIREMENT_SPEC,
            file_name="requirements.xlsx",
            storage_path="mock://requirements.xlsx",
        )


class RecordingGenerationService:
    def __init__(self) -> None:
        self.requests = []

    async def validate_source_documents(
        self,
        request,
        *,
        document_service,
        required_source_type=None,
    ) -> GenerationSourceValidationResult:
        return GenerationSourceValidationResult(
            project_id=request.project_id,
            target_artifact_type=request.target_artifact_type,
            required_source_type=required_source_type,
        )

    async def generate_artifact(self, request, **kwargs):
        self.requests.append(request)
        return GenerationResponse(
            project_id=request.project_id,
            message="artifact generated",
            result={
                "artifact": {
                    "artifact_id": "ART-WBS-CHAT",
                    "project_id": request.project_id,
                    "artifact_type": request.target_artifact_type.value,
                    "name": "WBS.xlsx",
                    "version": 1,
                    "source_document_ids": request.source_document_ids,
                    "result_json": {},
                    "status": "CREATED",
                    "storage_path": "mock://generated/WBS.xlsx",
                },
                "generated": {"artifact_type": request.target_artifact_type.value},
                "exported_file": {
                    "file_name": "WBS.xlsx",
                    "content_type": (
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    ),
                    "storage_path": "mock://generated/WBS.xlsx",
                },
            },
        )


class NoopScheduleService:
    async def extract_todos(self, *args, **kwargs):
        raise AssertionError("schedule service should not run in these tests")


def _generation_context() -> dict[str, Any]:
    return {
        "intent": "GENERATE_ARTIFACT",
        "target_artifact_type": ArtifactType.WBS.value,
        "source_document_type": DocumentType.REQUIREMENT_SPEC.value,
        "source_document_ids": ["DOC-REQ-CHAT"],
    }


def _make_orchestrator(
    *,
    repository: InMemoryConversationRepository | None = None,
    generation_service: RecordingGenerationService | None = None,
    initial_context: dict[str, Any] | None = None,
) -> tuple[ChatOrchestrator, InMemoryConversationRepository, RecordingGenerationService]:
    repository = repository or InMemoryConversationRepository()
    generation_service = generation_service or RecordingGenerationService()
    orchestrator = ChatOrchestrator(
        conversation_repository=repository,
        generation_service=generation_service,
        schedule_service=NoopScheduleService(),
        document_service=ChatDocumentService(),
        artifact_service=object(),
        retrieval_service=object(),
        template_service=object(),
        input_normalizer=CommandAwareInputNormalizer(
            initial_context or _generation_context()
        ),
    )
    return orchestrator, repository, generation_service


def _chat_request(
    message: str,
    *,
    conversation_id: str | None = None,
    action: ChatActionCommand | None = None,
) -> ChatMessageRequest:
    context = {}
    if action is None:
        context = {
            "start_date": "2026-01-01",
            "requirements_confirmed": True,
        }
    return ChatMessageRequest(
        project_id=PROJECT_ID,
        conversation_id=conversation_id,
        user_id="USER-001",
        message=message,
        action=action,
        context=context,
        permission_scope=list(DEFAULT_MVP_SCOPES),
    )


def _command(command_type: ChatCommandType, action_id: str) -> ChatActionCommand:
    return ChatActionCommand(
        type=command_type,
        action_id=action_id,
        payload={"action_id": action_id},
    )


@pytest.mark.anyio
async def test_chat_question_variant_does_not_prepare_generation_action() -> None:
    orchestrator, repository, generation_service = _make_orchestrator(
        initial_context={"intent": "GENERAL_QA", "topic": "REQUIREMENT_SPEC"}
    )

    response = await orchestrator.handle_message(
        _chat_request("What is a requirement spec?")
    )

    assert response.state == ChatState.IDLE
    assert repository.actions == {}
    assert generation_service.requests == []


@pytest.mark.anyio
async def test_chat_wrong_action_id_confirm_does_not_execute_pending_action() -> None:
    orchestrator, repository, generation_service = _make_orchestrator()

    first = await orchestrator.handle_message(_chat_request("Create WBS"))
    response = await orchestrator.handle_message(
        _chat_request(
            "Confirm another action",
            conversation_id=first.conversation_id,
            action=_command(ChatCommandType.CONFIRM_PENDING_ACTION, "ACT-NOT-FOUND"),
        )
    )

    assert response.state == ChatState.IDLE
    assert repository.actions[first.pending_action.action_id].status == (
        ChatActionStatus.WAITING_CONFIRMATION
    )
    assert generation_service.requests == []


@pytest.mark.anyio
async def test_chat_cancel_pending_action_prevents_generation() -> None:
    orchestrator, repository, generation_service = _make_orchestrator()

    first = await orchestrator.handle_message(_chat_request("Create WBS"))
    action_id = first.pending_action.action_id
    response = await orchestrator.handle_message(
        _chat_request(
            "Cancel",
            conversation_id=first.conversation_id,
            action=_command(ChatCommandType.CANCEL_PENDING_ACTION, action_id),
        )
    )

    assert response.state == ChatState.IDLE
    assert repository.actions[action_id].status == ChatActionStatus.CANCELLED
    assert generation_service.requests == []


@pytest.mark.anyio
async def test_chat_duplicate_confirm_executes_generation_only_once() -> None:
    orchestrator, repository, generation_service = _make_orchestrator()

    first = await orchestrator.handle_message(_chat_request("Create WBS"))
    action_id = first.pending_action.action_id
    first_confirm = await orchestrator.handle_message(
        _chat_request(
            "Confirm",
            conversation_id=first.conversation_id,
            action=_command(ChatCommandType.CONFIRM_PENDING_ACTION, action_id),
        )
    )
    duplicate_confirm = await orchestrator.handle_message(
        _chat_request(
            "Confirm again",
            conversation_id=first.conversation_id,
            action=_command(ChatCommandType.CONFIRM_PENDING_ACTION, action_id),
        )
    )

    assert first_confirm.state == ChatState.COMPLETED
    assert duplicate_confirm.state == ChatState.IDLE
    assert repository.actions[action_id].status == ChatActionStatus.EXECUTED
    assert len(generation_service.requests) == 1


@pytest.mark.anyio
async def test_chat_confirm_rejects_action_from_another_conversation() -> None:
    orchestrator, repository, generation_service = _make_orchestrator()

    first = await orchestrator.handle_message(_chat_request("Create WBS in first chat"))
    second = await orchestrator.handle_message(_chat_request("Create WBS in second chat"))
    response = await orchestrator.handle_message(
        _chat_request(
            "Confirm mismatched action",
            conversation_id=first.conversation_id,
            action=_command(
                ChatCommandType.CONFIRM_PENDING_ACTION,
                second.pending_action.action_id,
            ),
        )
    )

    assert response.state == ChatState.IDLE
    assert repository.actions[first.pending_action.action_id].status == (
        ChatActionStatus.WAITING_CONFIRMATION
    )
    assert repository.actions[second.pending_action.action_id].status == (
        ChatActionStatus.WAITING_CONFIRMATION
    )
    assert generation_service.requests == []


@pytest.mark.anyio
async def test_chat_confirm_ignores_tampered_payload_permission_scope() -> None:
    orchestrator, repository, generation_service = _make_orchestrator()

    first = await orchestrator.handle_message(_chat_request("Create WBS"))
    action_id = first.pending_action.action_id
    action = repository.actions[action_id]
    repository.actions[action_id] = action.model_copy(
        update={
            "payload": {
                **action.payload,
                "permission_scope": ["attacker:scope"],
            }
        }
    )

    response = await orchestrator.handle_message(
        _chat_request(
            "Confirm",
            conversation_id=first.conversation_id,
            action=_command(ChatCommandType.CONFIRM_PENDING_ACTION, action_id),
        )
    )

    assert response.state == ChatState.COMPLETED
    assert generation_service.requests[-1].permission_scope == DEFAULT_MVP_SCOPES
