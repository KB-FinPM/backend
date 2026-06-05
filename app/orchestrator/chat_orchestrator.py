# EN: Orchestrates chat messages, pending actions, and delegated PM workflows.

from typing import Any
from uuid import uuid4

from app.core.logger import get_logger
from app.orchestrator.input_orchestrator import InputOrchestrator, input_orchestrator
from app.orchestrator.output_orchestrator import (
    OutputOrchestrator,
    output_orchestrator,
)
from app.repositories.conversation_repository import ConversationRepository
from app.schemas.artifact import ArtifactType, DocumentType
from app.schemas.chat import (
    ChatActionMetadata,
    ChatActionStatus,
    ChatActionType,
    ChatCommandType,
    ChatMessageRequest,
    ChatResponse,
    ChatRole,
    ChatState,
    ConversationMetadata,
)
from app.schemas.io_agent import (
    InputAgentRequest,
    InputType,
    OutputAgentRequest,
    OutputResponseType,
)
from app.schemas.request import GenerationRequest, ScheduleTodoRequest
from app.schemas.response import GenerationResponse, ScheduleTodoResponse
from app.services.artifact_service import ArtifactService
from app.services.document_service import DocumentService
from app.services.generation_service import GenerationService
from app.services.schedule_service import ScheduleService
from app.services.template_service import TemplateService

logger = get_logger(__name__)


class ChatOrchestrator:
    """Coordinates chat state while delegating PM work to existing services."""

    def __init__(
        self,
        *,
        conversation_repository: ConversationRepository,
        generation_service: GenerationService,
        schedule_service: ScheduleService,
        document_service: DocumentService,
        artifact_service: ArtifactService,
        retrieval_service: Any,
        template_service: TemplateService,
        input_normalizer: InputOrchestrator = input_orchestrator,
        output_formatter: OutputOrchestrator = output_orchestrator,
    ) -> None:
        self.conversation_repository = conversation_repository
        self.generation_service = generation_service
        self.schedule_service = schedule_service
        self.document_service = document_service
        self.artifact_service = artifact_service
        self.retrieval_service = retrieval_service
        self.template_service = template_service
        self.input_normalizer = input_normalizer
        self.output_formatter = output_formatter

    async def handle_message(self, request: ChatMessageRequest) -> ChatResponse:
        conversation = await self._resolve_conversation(request)
        await self.conversation_repository.add_message(
            message_id=self._new_id("MSG"),
            conversation_id=conversation.conversation_id,
            project_id=request.project_id,
            role=ChatRole.USER,
            content=request.message,
            structured_payload={
                "context": request.context,
                "action": request.action.model_dump(mode="json")
                if request.action
                else None,
            },
        )

        input_response = await self.input_normalizer.normalize(
            InputAgentRequest(
                project_id=request.project_id,
                user_id=request.user_id,
                permission_scope=request.permission_scope,
                input_type=InputType.TEXT,
                raw_payload={
                    "message": request.message,
                    "action": request.action.model_dump(mode="json")
                    if request.action
                    else None,
                },
                context=request.context,
            )
        )
        if not input_response.success:
            return await self._render_and_save_response(
                conversation=conversation,
                project_id=request.project_id,
                result_json={
                    "event": "ACTION_FAILED",
                    "error": input_response.error,
                    "result": {"validation_errors": input_response.validation_errors},
                },
            )

        structured_context = input_response.structured_context
        intent = structured_context.get("intent")
        if intent == "CONFIRM_PENDING_ACTION":
            return await self._confirm_pending_action(
                conversation=conversation,
                project_id=request.project_id,
                action_id=structured_context.get("action_id"),
            )

        if intent == "CANCEL_PENDING_ACTION":
            return await self._cancel_pending_action(
                conversation=conversation,
                project_id=request.project_id,
                action_id=structured_context.get("action_id"),
            )

        if intent == "GENERATE_ARTIFACT":
            return await self._prepare_generation_action(
                conversation=conversation,
                request=request,
                structured_context=structured_context,
            )

        if intent == "EXTRACT_ACTION_ITEMS":
            return await self._prepare_schedule_action(
                conversation=conversation,
                request=request,
                structured_context=structured_context,
            )

        return await self._render_and_save_response(
            conversation=conversation,
            project_id=request.project_id,
            result_json={"event": "GENERAL_QA"},
        )

    async def _resolve_conversation(
        self,
        request: ChatMessageRequest,
    ) -> ConversationMetadata:
        if request.conversation_id:
            existing = await self.conversation_repository.get_conversation(
                project_id=request.project_id,
                conversation_id=request.conversation_id,
            )
            if existing is not None:
                return existing

        conversation_id = request.conversation_id or self._new_id("CONV")
        return await self.conversation_repository.create_conversation(
            conversation_id=conversation_id,
            project_id=request.project_id,
            user_id=request.user_id,
            title=request.message[:80],
        )

    async def _prepare_generation_action(
        self,
        *,
        conversation: ConversationMetadata,
        request: ChatMessageRequest,
        structured_context: dict[str, Any],
    ) -> ChatResponse:
        source_document_ids = structured_context.get("source_document_ids") or []
        if not source_document_ids:
            return await self._render_and_save_response(
                conversation=conversation,
                project_id=request.project_id,
                result_json={"event": "REQUIRED_INFO"},
            )

        target_artifact_type = ArtifactType(structured_context["target_artifact_type"])
        validation_error = await self._validate_generation_documents(
            project_id=request.project_id,
            source_document_ids=source_document_ids,
            target_artifact_type=target_artifact_type,
        )
        if validation_error:
            return await self._render_and_save_response(
                conversation=conversation,
                project_id=request.project_id,
                result_json={
                    "event": "ACTION_FAILED",
                    "error": validation_error,
                    "result": {},
                },
            )

        payload = {
            "project_id": request.project_id,
            "target_artifact_type": target_artifact_type.value,
            "source_document_ids": source_document_ids,
            "source_document_type": structured_context.get("source_document_type"),
            "query": request.message,
            "permission_scope": request.permission_scope,
            "template_id": request.context.get("template_id"),
            "template_version": request.context.get("template_version"),
        }
        pending_action = await self.conversation_repository.create_action(
            action_id=self._new_id("ACT"),
            conversation_id=conversation.conversation_id,
            project_id=request.project_id,
            action_type=self._action_type_for_artifact(target_artifact_type),
            payload=payload,
        )
        return await self._render_and_save_response(
            conversation=conversation,
            project_id=request.project_id,
            result_json={
                "event": "CONFIRMATION_REQUIRED",
                "pending_action": pending_action.model_dump(mode="json"),
            },
            pending_action=pending_action,
        )

    async def _prepare_schedule_action(
        self,
        *,
        conversation: ConversationMetadata,
        request: ChatMessageRequest,
        structured_context: dict[str, Any],
    ) -> ChatResponse:
        pending_action = await self.conversation_repository.create_action(
            action_id=self._new_id("ACT"),
            conversation_id=conversation.conversation_id,
            project_id=request.project_id,
            action_type=ChatActionType.EXTRACT_ACTION_ITEMS,
            payload={
                "project_id": request.project_id,
                "meeting_notes": structured_context.get("meeting_notes")
                or request.message,
                "source_document_ids": structured_context.get("source_document_ids")
                or [],
                "user_id": request.user_id,
                "permission_scope": request.permission_scope,
            },
        )
        return await self._render_and_save_response(
            conversation=conversation,
            project_id=request.project_id,
            result_json={
                "event": "CONFIRMATION_REQUIRED",
                "pending_action": pending_action.model_dump(mode="json"),
            },
            pending_action=pending_action,
        )

    async def _confirm_pending_action(
        self,
        *,
        conversation: ConversationMetadata,
        project_id: str,
        action_id: str | None = None,
    ) -> ChatResponse:
        pending_action = await self._resolve_pending_action(
            project_id=project_id,
            conversation_id=conversation.conversation_id,
            action_id=action_id,
        )
        if pending_action is None:
            return await self._render_and_save_response(
                conversation=conversation,
                project_id=project_id,
                result_json={
                    "event": "ACTION_FAILED",
                    "error": "실행 대기 중인 작업이 없습니다.",
                    "result": {},
                },
            )

        await self.conversation_repository.update_action_status(
            project_id=project_id,
            action_id=pending_action.action_id,
            status=ChatActionStatus.EXECUTING,
        )
        response = await self._execute_action(pending_action)
        response_payload = response.model_dump(mode="json")
        if not response.success:
            failed_action = await self.conversation_repository.update_action_status(
                project_id=project_id,
                action_id=pending_action.action_id,
                status=ChatActionStatus.FAILED,
                result_json=response_payload,
            )
            return await self._render_and_save_response(
                conversation=conversation,
                project_id=project_id,
                result_json={
                    "event": "ACTION_FAILED",
                    "error": response.message,
                    "result": response_payload,
                },
                pending_action=failed_action,
            )

        completed_action = await self.conversation_repository.update_action_status(
            project_id=project_id,
            action_id=pending_action.action_id,
            status=ChatActionStatus.EXECUTED,
            result_json=response_payload,
        )
        return await self._render_and_save_response(
            conversation=conversation,
            project_id=project_id,
            result_json={
                "event": "ACTION_COMPLETED",
                "result": response.result if isinstance(response.result, dict) else {},
            },
            pending_action=completed_action,
        )

    async def _cancel_pending_action(
        self,
        *,
        conversation: ConversationMetadata,
        project_id: str,
        action_id: str | None = None,
    ) -> ChatResponse:
        pending_action = await self._resolve_pending_action(
            project_id=project_id,
            conversation_id=conversation.conversation_id,
            action_id=action_id,
        )
        if pending_action is not None:
            pending_action = await self.conversation_repository.update_action_status(
                project_id=project_id,
                action_id=pending_action.action_id,
                status=ChatActionStatus.CANCELLED,
            )

        return await self._render_and_save_response(
            conversation=conversation,
            project_id=project_id,
            result_json={"event": "ACTION_CANCELLED"},
            pending_action=pending_action,
        )

    async def _resolve_pending_action(
        self,
        *,
        project_id: str,
        conversation_id: str,
        action_id: str | None,
    ) -> ChatActionMetadata | None:
        if action_id:
            action = await self.conversation_repository.get_action(
                project_id=project_id,
                action_id=action_id,
            )
            if action is None or action.status != ChatActionStatus.WAITING_CONFIRMATION:
                return None
            return action

        return await self.conversation_repository.get_latest_waiting_action(
            project_id=project_id,
            conversation_id=conversation_id,
        )

    async def _execute_action(
        self,
        action: ChatActionMetadata,
    ) -> GenerationResponse | ScheduleTodoResponse:
        if action.action_type in {
            ChatActionType.GENERATE_REQUIREMENT,
            ChatActionType.GENERATE_WBS,
            ChatActionType.GENERATE_SCREEN_DESIGN,
        }:
            return await self._execute_generation_action(action)

        return await self._execute_schedule_action(action)

    async def _execute_generation_action(
        self,
        action: ChatActionMetadata,
    ) -> GenerationResponse:
        payload = action.payload
        generation_request = GenerationRequest(
            project_id=payload["project_id"],
            source_document_ids=payload.get("source_document_ids") or [],
            source_document_type=payload.get("source_document_type"),
            target_artifact_type=payload["target_artifact_type"],
            template_id=payload.get("template_id"),
            template_version=payload.get("template_version"),
            query=payload.get("query"),
            permission_scope=payload.get("permission_scope") or ["project:read"],
        )
        return await self.generation_service.generate_artifact(
            generation_request,
            artifact_service=self.artifact_service,
            retrieval_service=self.retrieval_service,
            template_service=self.template_service,
        )

    async def _execute_schedule_action(
        self,
        action: ChatActionMetadata,
    ) -> ScheduleTodoResponse:
        payload = action.payload
        schedule_request = ScheduleTodoRequest(
            project_id=payload["project_id"],
            meeting_notes=payload.get("meeting_notes") or "",
            source_document_ids=payload.get("source_document_ids") or [],
            user_id=payload.get("user_id"),
            permission_scope=payload.get("permission_scope") or ["project:read"],
        )
        return await self.schedule_service.extract_todos(
            schedule_request,
            structured_context={"source": "chat", "action_id": action.action_id},
        )

    async def _validate_generation_documents(
        self,
        *,
        project_id: str,
        source_document_ids: list[str],
        target_artifact_type: ArtifactType,
    ) -> str | None:
        required_type = None
        if target_artifact_type in {ArtifactType.WBS, ArtifactType.SCREEN_DESIGN}:
            required_type = DocumentType.REQUIREMENT_SPEC

        missing_document_ids: list[str] = []
        invalid_documents: list[str] = []
        for document_id in source_document_ids:
            document = await self.document_service.get_document(
                project_id=project_id,
                document_id=document_id,
            )
            if document is None:
                missing_document_ids.append(document_id)
                continue
            if required_type is not None and document.document_type != required_type:
                invalid_documents.append(document_id)

        if missing_document_ids:
            return f"문서를 찾을 수 없습니다: {', '.join(missing_document_ids)}"
        if invalid_documents and required_type is not None:
            return (
                f"{target_artifact_type.value} 생성에는 {required_type.value} "
                f"문서가 필요합니다: {', '.join(invalid_documents)}"
            )
        return None

    async def _render_and_save_response(
        self,
        *,
        conversation: ConversationMetadata,
        project_id: str,
        result_json: dict[str, Any],
        pending_action: ChatActionMetadata | None = None,
    ) -> ChatResponse:
        output_response = await self.output_formatter.format(
            OutputAgentRequest(
                project_id=project_id,
                response_type=OutputResponseType.CHAT_RESPONSE,
                result_json=result_json,
                message="ok",
            )
        )
        display_payload = output_response.display_payload
        assistant_message = await self.conversation_repository.add_message(
            message_id=self._new_id("MSG"),
            conversation_id=conversation.conversation_id,
            project_id=project_id,
            role=ChatRole.ASSISTANT,
            content=output_response.message,
            structured_payload=display_payload,
        )
        return ChatResponse(
            conversation_id=conversation.conversation_id,
            message_id=assistant_message.message_id,
            message=output_response.message,
            state=ChatState(display_payload.get("state", ChatState.IDLE.value)),
            pending_action=pending_action,
            suggested_actions=display_payload.get("suggested_actions") or [],
            result=display_payload.get("result") or {},
        )

    def _action_type_for_artifact(self, artifact_type: ArtifactType) -> ChatActionType:
        mapping = {
            ArtifactType.REQUIREMENT_SPEC: ChatActionType.GENERATE_REQUIREMENT,
            ArtifactType.WBS: ChatActionType.GENERATE_WBS,
            ArtifactType.SCREEN_DESIGN: ChatActionType.GENERATE_SCREEN_DESIGN,
        }
        return mapping[artifact_type]

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:12].upper()}"
