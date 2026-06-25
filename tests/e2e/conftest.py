from __future__ import annotations

from typing import Any

import pytest

from app.orchestrator.chat_orchestrator import ChatOrchestrator
from app.orchestrator.schedule_orchestrator import ScheduleOrchestrator
from app.schemas.artifact import (
    ArtifactMetadata,
    ArtifactStatus,
    ArtifactType,
    DocumentMetadata,
    DocumentType,
)
from app.schemas.chat import (
    ChatActionMetadata,
    ChatActionStatus,
    ChatMessageMetadata,
    ChatRole,
    ConversationMetadata,
)
from app.schemas.response import GenerationResponse
from app.services.generation_service import GenerationSourceValidationResult
from app.services.schedule_service import ScheduleService


PROJECT_ID = "PRJ-TEST-001"


def assert_user_facing_message(message: str) -> None:
    blocked_fragments = [
        "Input Agent",
        "Output Agent",
        "GenerationOrchestrator",
        "GENERATE_ARTIFACT",
        "SCHEDULE_QUERY",
        "structured_context",
        "traceback",
    ]
    lowered = message.lower()
    assert message.strip()
    for fragment in blocked_fragments:
        assert fragment.lower() not in lowered


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


class ScenarioDocumentService:
    def __init__(self) -> None:
        self.documents: dict[str, DocumentMetadata] = {}
        self.add_document(
            document_id="DOC-RFP-001",
            document_type=DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION,
            file_name="kb-rfp.txt",
        )
        self.add_document(
            document_id="DOC-REQ-001",
            document_type=DocumentType.REQUIREMENT_SPEC,
            file_name="kb-requirement-spec.xlsx",
        )

    def add_document(
        self,
        *,
        document_id: str,
        document_type: DocumentType,
        file_name: str,
    ) -> DocumentMetadata:
        document = DocumentMetadata(
            document_id=document_id,
            project_id=PROJECT_ID,
            document_type=document_type,
            file_name=file_name,
            storage_path=f"mock://documents/{document_id}/{file_name}",
        )
        self.documents[document_id] = document
        return document

    async def get_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> DocumentMetadata | None:
        document = self.documents.get(document_id)
        if document and document.project_id == project_id:
            return document
        return None


class ScenarioGenerationService:
    def __init__(self) -> None:
        self.requests = []

    async def validate_source_documents(
        self,
        request,
        *,
        document_service,
        required_source_type=None,
    ) -> GenerationSourceValidationResult:
        missing = []
        invalid = []
        if required_source_type is None and request.target_artifact_type in {
            ArtifactType.WBS,
            ArtifactType.SCREEN_DESIGN,
            ArtifactType.UNITTEST_SPEC,
        }:
            required_source_type = DocumentType.REQUIREMENT_SPEC

        for document_id in request.source_document_ids:
            document = await document_service.get_document(
                project_id=request.project_id,
                document_id=document_id,
            )
            if document is None:
                missing.append(document_id)
            elif required_source_type and document.document_type != required_source_type:
                invalid.append(
                    {
                        "document_id": document.document_id,
                        "document_type": document.document_type.value,
                        "required_document_type": required_source_type.value,
                    }
                )

        return GenerationSourceValidationResult(
            project_id=request.project_id,
            target_artifact_type=request.target_artifact_type,
            required_source_type=required_source_type,
            missing_document_ids=missing,
            invalid_type_documents=invalid,
        )

    async def generate_artifact(
        self,
        request,
        *,
        artifact_service=None,
        retrieval_service=None,
        template_service=None,
        document_service=None,
    ) -> GenerationResponse:
        self.requests.append(request)
        artifact_type = request.target_artifact_type.value
        artifact_id = f"ART-{artifact_type}-001"
        file_name = {
            ArtifactType.REQUIREMENT_SPEC.value: "요구사항명세서.xlsx",
            ArtifactType.WBS.value: "WBS.xlsx",
            ArtifactType.SCREEN_DESIGN.value: "화면기획서.pptx",
            ArtifactType.UNITTEST_SPEC.value: "단위테스트케이스.xlsx",
        }.get(
            artifact_type,
            f"{artifact_type}.xlsx",
        )
        generated = self._generated_payload(artifact_type)
        return GenerationResponse(
            project_id=request.project_id,
            message="artifact generated",
            result={
                "artifact": {
                    "artifact_id": artifact_id,
                    "project_id": request.project_id,
                    "artifact_type": artifact_type,
                    "name": file_name,
                    "version": 1,
                    "source_document_ids": request.source_document_ids,
                    "result_json": generated,
                    "status": ArtifactStatus.CREATED.value,
                    "storage_path": f"mock://generated/{artifact_id}/{file_name}",
                },
                "generated": generated,
                "exported_file": {
                    "file_name": file_name,
                    "content_type": (
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    ),
                    "storage_path": f"mock://generated/{artifact_id}/{file_name}",
                },
            },
        )

    def _generated_payload(self, artifact_type: str) -> dict[str, Any]:
        if artifact_type == ArtifactType.REQUIREMENT_SPEC.value:
            return {
                "artifact_type": artifact_type,
                "requirements": [
                    {
                        "requirement_id": "REQ-001",
                        "title": "Mobile login",
                        "description": "Users can sign in on mobile.",
                    }
                ],
            }
        if artifact_type == ArtifactType.WBS.value:
            return {
                "artifact_type": artifact_type,
                "tasks": [
                    {
                        "task_id": "WBS-001",
                        "name": "Requirement analysis",
                        "planned_start_date": "2024-01-10",
                        "planned_end_date": "2024-01-31",
                        "metadata": {
                            "level": "1",
                            "start_date": "2024-01-10",
                            "end_date": "2024-01-31",
                        },
                    }
                ],
            }
        return {"artifact_type": artifact_type}


class InMemoryActionItemRepository:
    def __init__(self) -> None:
        self.todos: dict[str, list[dict[str, Any]]] = {
            PROJECT_ID: [
                {
                    "todo_id": "TODO-001",
                    "title": "Requirement review",
                    "assignee": "PM",
                    "due_date": "2026-06-10",
                    "status": "TODO",
                    "related_document": "WBS",
                }
            ]
        }

    async def list_project_todos(self, *, project_id: str) -> list[dict[str, Any]]:
        return [dict(todo) for todo in self.todos.get(project_id, [])]

    async def save_extracted_todos(
        self,
        *,
        project_id: str,
        todos: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        saved = []
        for index, todo in enumerate(todos, start=1):
            saved_todo = {
                **todo,
                "todo_id": todo.get("todo_id") or f"TODO-SAVED-{index:03d}",
                "project_id": project_id,
            }
            saved.append(saved_todo)
        self.todos.setdefault(project_id, []).extend(saved)
        return saved

    async def complete_todo_by_id(
        self,
        *,
        project_id: str,
        todo_id: str,
    ) -> dict[str, Any] | None:
        for todo in self.todos.get(project_id, []):
            if todo.get("todo_id") == todo_id:
                todo["status"] = "DONE"
                return dict(todo)
        return None


@pytest.fixture
def scenario_services():
    conversation_repository = InMemoryConversationRepository()
    document_service = ScenarioDocumentService()
    generation_service = ScenarioGenerationService()
    action_item_repository = InMemoryActionItemRepository()
    schedule_service = ScheduleService(
        orchestrator=ScheduleOrchestrator(),
        action_item_repository=action_item_repository,
    )
    orchestrator = ChatOrchestrator(
        conversation_repository=conversation_repository,
        generation_service=generation_service,
        schedule_service=schedule_service,
        document_service=document_service,
        artifact_service=object(),
        retrieval_service=object(),
        template_service=object(),
    )
    return {
        "chat_orchestrator": orchestrator,
        "conversation_repository": conversation_repository,
        "document_service": document_service,
        "generation_service": generation_service,
        "action_item_repository": action_item_repository,
    }
