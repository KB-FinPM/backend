# EN: Tests for chat orchestration over pending PM actions.

import pytest

from app.orchestrator.chat_orchestrator import ChatOrchestrator
from app.schemas.artifact import (
    ArtifactMetadata,
    ArtifactType,
    DocumentMetadata,
    DocumentType,
)
from app.schemas.chat import (
    ChatActionStatus,
    ChatActionType,
    ChatCommandType,
    ChatMessageRequest,
    ChatRole,
)
from app.schemas.io_agent import InputAgentResponse, NormalizedRequestType
from app.schemas.response import GenerationResponse, ScheduleTodoResponse
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

    async def get_latest_message_by_role(self, *, project_id, conversation_id, role):
        for message in reversed(self.messages):
            if (
                message.project_id == project_id
                and message.conversation_id == conversation_id
                and message.role == role
            ):
                return message
        return None

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

    async def list_documents(self, *, project_id):
        return [
            DocumentMetadata(
                document_id="DOC-REQ-001",
                project_id=project_id,
                document_type=DocumentType.REQUIREMENT_SPEC,
                file_name="requirement.txt",
                storage_path="s3://bucket/requirement.txt",
            )
        ]


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


class SpyScheduleServiceForTodoMutation:
    def __init__(self) -> None:
        self.complete_calls = 0
        self.query_calls = []

    async def complete_todo(self, **kwargs):
        self.complete_calls += 1
        raise AssertionError("chat flow must not complete TODOs")

    async def run_query(
        self,
        *,
        project_id,
        schedule_action,
        context,
        permission_scope=None,
        persist_wbs_todos=True,
    ):
        self.query_calls.append(
            {
                "project_id": project_id,
                "schedule_action": schedule_action,
                "context": context,
                "permission_scope": permission_scope,
                "persist_wbs_todos": persist_wbs_todos,
            }
        )
        return ScheduleTodoResponse(
            project_id=project_id,
            message="todo query",
            result={
                "artifact_type": "SCHEDULE_TODO_LIST",
                "action": schedule_action,
                "status": "SUCCESS",
                "todos": [
                    {
                        "todo_id": "TODO-001",
                        "title": "Review requirement",
                        "source_type": "MEETING_NOTES",
                        "status": "TODO",
                    }
                ],
                "assistant_message": "채팅에서는 TODO 완료처리를 지원하지 않습니다.",
                "metadata": {
                    "source_filter": "ALL",
                    "status_filter": "NOT_DONE",
                },
            },
        )


class StubArtifactService:
    async def list_artifacts(self, *, project_id):
        return [
            ArtifactMetadata(
                artifact_id="ART-WBS-001",
                project_id=project_id,
                artifact_type=ArtifactType.WBS,
                name="프로젝트 WBS",
                source_document_ids=["DOC-REQ-001"],
            )
        ]


class StubActionItemRepository:
    async def list_project_todos(self, *, project_id):
        return [
            {
                "todo_id": "TODO-001",
                "title": "설계 및 테스트",
                "status": "TODO",
            }
        ]


class StubScheduleServiceWithTodos:
    def __init__(self) -> None:
        self.action_item_repository = StubActionItemRepository()


class SpyInputNormalizer:
    def __init__(self) -> None:
        self.received_request = None

    async def normalize(self, request):
        self.received_request = request
        return InputAgentResponse(
            agent_name="SpyInputNormalizer",
            normalized_request_type=NormalizedRequestType.CHAT_MESSAGE,
            structured_context={"intent": "GENERAL_QA"},
        )


class CompleteTodoInputNormalizer:
    async def normalize(self, request):
        return InputAgentResponse(
            agent_name="CompleteTodoInputNormalizer",
            normalized_request_type=NormalizedRequestType.CHAT_MESSAGE,
            structured_context={
                "intent": "COMPLETE_TODO",
                "action": "UPDATE",
                "schedule_action": "COMPLETE_TODO",
                "todo_title_query": "Review requirement",
                "entities": {"todo_title": "Review requirement"},
            },
        )


class ScheduleQueryInputNormalizer:
    async def normalize(self, request):
        return InputAgentResponse(
            agent_name="ScheduleQueryInputNormalizer",
            normalized_request_type=NormalizedRequestType.CHAT_MESSAGE,
            structured_context={
                "intent": "SCHEDULE_QUERY",
                "action": "QUERY",
                "schedule_action": "SHOW_TODAY_TODOS",
                "entities": {"time_filter": "TODAY"},
            },
        )


@pytest.mark.anyio
async def test_chat_orchestrator_guides_chat_todo_completion_to_sidebar() -> None:
    schedule_service = SpyScheduleServiceForTodoMutation()
    orchestrator = ChatOrchestrator(
        conversation_repository=StubConversationRepository(),
        generation_service=StubGenerationService(),
        schedule_service=schedule_service,
        document_service=StubDocumentService(),
        artifact_service=StubArtifactService(),
        retrieval_service=object(),
        template_service=object(),
        input_normalizer=CompleteTodoInputNormalizer(),
    )

    response = await orchestrator.handle_message(
        ChatMessageRequest(
            project_id="PRJ-001",
            user_id="USER-001",
            message="Review requirement 완료했어",
        )
    )

    assert response.state == "IDLE"
    assert schedule_service.complete_calls == 0
    assert schedule_service.query_calls == []
    assert response.result["todo_management"] is True
    assert "할일 관리" in response.message


@pytest.mark.anyio
async def test_chat_orchestrator_allows_read_only_schedule_query() -> None:
    schedule_service = SpyScheduleServiceForTodoMutation()
    orchestrator = ChatOrchestrator(
        conversation_repository=StubConversationRepository(),
        generation_service=StubGenerationService(),
        schedule_service=schedule_service,
        document_service=StubDocumentService(),
        artifact_service=StubArtifactService(),
        retrieval_service=object(),
        template_service=object(),
        input_normalizer=ScheduleQueryInputNormalizer(),
    )

    response = await orchestrator.handle_message(
        ChatMessageRequest(
            project_id="PRJ-001",
            user_id="USER-001",
            message="오늘 할일 알려줘",
        )
    )

    assert response.state == "COMPLETED"
    assert schedule_service.complete_calls == 0
    assert len(schedule_service.query_calls) == 1
    assert schedule_service.query_calls[0]["schedule_action"] == "SHOW_TODAY_TODOS"
    assert schedule_service.query_calls[0]["persist_wbs_todos"] is False
    assert response.result["items"][0]["title"] == "Review requirement"
    assert response.result["items"][0]["actions"] == []


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
            context={
                "selected_document_ids": ["DOC-REQ-001"],
                "start_date": "2025-01-20",
                "requirements_confirmed": True,
            },
        )
    )
    assert first_response.state == "COMPLETED"
    assert generation_service.received_request is not None
    assert generation_service.received_request.target_artifact_type == "WBS"


@pytest.mark.anyio
async def test_chat_orchestrator_returns_download_file_for_recent_artifact() -> None:
    orchestrator = ChatOrchestrator(
        conversation_repository=StubConversationRepository(),
        generation_service=StubGenerationService(),
        schedule_service=StubScheduleService(),
        document_service=StubDocumentService(),
        artifact_service=StubArtifactService(),
        retrieval_service=object(),
        template_service=object(),
    )

    response = await orchestrator.handle_message(
        ChatMessageRequest(
            project_id="PRJ-001",
            user_id="USER-001",
            message="download latest WBS as xlsx",
        )
    )

    assert response.state == "COMPLETED"
    assert response.download_files == [
        {
            "artifact_id": "ART-WBS-001",
            "artifact_type": "WBS",
            "file_name": "WBS.xlsx",
            "mime_type": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            "content_type": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        }
    ]


@pytest.mark.anyio
async def test_chat_orchestrator_requests_artifact_for_ambiguous_download() -> None:
    class EmptyArtifactService:
        async def list_artifacts(self, *, project_id):
            return []

    orchestrator = ChatOrchestrator(
        conversation_repository=StubConversationRepository(),
        generation_service=StubGenerationService(),
        schedule_service=StubScheduleService(),
        document_service=StubDocumentService(),
        artifact_service=EmptyArtifactService(),
        retrieval_service=object(),
        template_service=object(),
    )

    response = await orchestrator.handle_message(
        ChatMessageRequest(
            project_id="PRJ-001",
            user_id="USER-001",
            message="download export file",
        )
    )

    assert response.state == "WAITING_REQUIRED_INFO"
    assert response.download_files == []
    assert response.result["missing_fields"] == ["artifact_id"]


@pytest.mark.anyio
async def test_chat_orchestrator_enriches_input_agent_project_context() -> None:
    repository = StubConversationRepository()
    conversation = await repository.create_conversation(
        conversation_id="CONV-001",
        project_id="PRJ-001",
        user_id="USER-001",
    )
    pending_action = await repository.create_action(
        action_id="ACT-001",
        conversation_id=conversation.conversation_id,
        project_id=conversation.project_id,
        action_type=ChatActionType.GENERATE_WBS,
        status=ChatActionStatus.WAITING_CONFIRMATION,
        payload={"target_artifact_type": "WBS"},
    )
    await repository.add_message(
        message_id="MSG-AST-001",
        conversation_id=conversation.conversation_id,
        project_id=conversation.project_id,
        role=ChatRole.ASSISTANT,
        content="이번 주 할일 1건을 찾았습니다.",
        structured_payload={
            "state": "COMPLETED",
            "display_type": "schedule_todos",
            "result": {
                "action": "SHOW_THIS_WEEK_TODOS",
                "status": "SUCCESS",
                "metadata": {"todo_count": 1},
            },
        },
    )
    input_normalizer = SpyInputNormalizer()
    orchestrator = ChatOrchestrator(
        conversation_repository=repository,
        generation_service=StubGenerationService(),
        schedule_service=StubScheduleServiceWithTodos(),
        document_service=StubDocumentService(),
        artifact_service=StubArtifactService(),
        retrieval_service=object(),
        template_service=object(),
        input_normalizer=input_normalizer,
    )

    await orchestrator.handle_message(
        ChatMessageRequest(
            project_id="PRJ-001",
            conversation_id=conversation.conversation_id,
            user_id="USER-001",
            message="WBS 기준으로 할 일 알려줘",
        )
    )

    context = input_normalizer.received_request.context
    assert context["current_project_id"] == "PRJ-001"
    assert context["uploaded_documents"][0]["document_id"] == "DOC-REQ-001"
    assert context["generated_artifacts"][0]["artifact_type"] == "WBS"
    assert context["recent_todos"][0]["title"] == "설계 및 테스트"
    assert context["pending_action"]["action_id"] == pending_action.action_id
    assert context["last_agent_response_summary"]["action"] == "SHOW_THIS_WEEK_TODOS"
    assert context["last_agent_response_summary"]["todo_count"] == 1


@pytest.mark.anyio
async def test_chat_orchestrator_cancel_meeting_todo_action_does_not_request_upload() -> None:
    repository = StubConversationRepository()
    conversation = await repository.create_conversation(
        conversation_id="CONV-MEETING-001",
        project_id="PRJ-001",
        user_id="USER-001",
    )
    pending_action = await repository.create_action(
        action_id="ACT-MEETING-001",
        conversation_id=conversation.conversation_id,
        project_id=conversation.project_id,
        action_type=ChatActionType.EXTRACT_ACTION_ITEMS,
        status=ChatActionStatus.WAITING_CONFIRMATION,
        payload={
            "project_id": "PRJ-001",
            "schedule_action": "EXTRACT_TODOS_FROM_MEETING",
            "source_document_ids": ["DOC-MEETING-001"],
        },
    )
    orchestrator = ChatOrchestrator(
        conversation_repository=repository,
        generation_service=StubGenerationService(),
        schedule_service=StubScheduleService(),
        document_service=StubDocumentService(),
        artifact_service=StubArtifactService(),
        retrieval_service=object(),
        template_service=object(),
    )

    response = await orchestrator.handle_message(
        ChatMessageRequest(
            project_id="PRJ-001",
            conversation_id=conversation.conversation_id,
            user_id="USER-001",
            message="다른 회의록 업로드",
            action={
                "type": ChatCommandType.CANCEL_PENDING_ACTION,
                "action_id": pending_action.action_id,
                "payload": {"action_id": pending_action.action_id},
            },
        )
    )

    assert response.state == "IDLE"
    assert repository.actions[pending_action.action_id].status == ChatActionStatus.CANCELLED
    assert "upload_request" not in response.result
