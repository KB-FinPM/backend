# EN: Orchestrates chat messages, pending actions, and delegated PM workflows.

import asyncio
from typing import Any
from uuid import uuid4

from app.core.auth import DEFAULT_MVP_SCOPES
from app.orchestrator.input_orchestrator import InputOrchestrator, input_orchestrator
from app.orchestrator.output_orchestrator import (
    OutputOrchestrator,
    output_orchestrator,
)
from app.repositories.conversation_repository import ConversationRepository
from app.schemas.artifact import ArtifactType
from app.schemas.chat import (
    ChatActionMetadata,
    ChatActionStatus,
    ChatActionType,
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
from app.services.generation_job_service import (
    is_generation_action,
    run_generation_action_job,
)
from app.services.schedule_service import ScheduleService
from app.services.template_service import TemplateService


class ChatOrchestrator:
    """Central PM workflow controller for conversational requests.

    The orchestrator owns project context lookup, Input Agent invocation,
    downstream agent/service selection, and Output Agent rendering. Input Agent
    results are treated as semantic analysis only, never as executable control
    flow outside this class.
    """

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

        input_context = await self._build_input_context(
            conversation=conversation,
            request=request,
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
                context=input_context,
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

        if intent == "CLARIFICATION_REQUIRED":
            return await self._render_and_save_response(
                conversation=conversation,
                project_id=request.project_id,
                result_json={
                    "event": "CLARIFICATION_REQUIRED",
                    "question": structured_context.get("clarification_question"),
                    "semantic_slots": structured_context.get("semantic_slots") or {},
                },
            )

        if intent == "GENERATE_ARTIFACT":
            return await self._prepare_generation_action(
                conversation=conversation,
                request=request,
                structured_context=structured_context,
            )

        if intent == "EXTRACT_ACTION_ITEMS":
            if structured_context.get("missing_slots"):
                return await self._render_and_save_response(
                    conversation=conversation,
                    project_id=request.project_id,
                    result_json={
                        "event": "SCHEDULE_RESULT",
                        "result": {
                            "artifact_type": "SCHEDULE_TODO_LIST",
                            "action": structured_context.get("schedule_action")
                            or "EXTRACT_TODOS_FROM_MEETING",
                            "status": "REQUIRED_INFO",
                            "missing_fields": structured_context.get("missing_slots")
                            or [],
                            "metadata": {"required_context": "MEETING_NOTES"},
                        },
                    },
                )
            return await self._prepare_schedule_action(
                conversation=conversation,
                request=request,
                structured_context=structured_context,
            )

        if intent == "SCHEDULE_QUERY":
            schedule_action = str(
                structured_context.get("schedule_action") or ""
            ).strip()
            if schedule_action == "EXTRACT_TODOS_FROM_MEETING":
                return await self._prepare_schedule_action(
                    conversation=conversation,
                    request=request,
                    structured_context=structured_context,
                )
            return await self._run_schedule_query(
                conversation=conversation,
                request=request,
                structured_context=structured_context,
            )

        if intent == "COMPLETE_TODO":
            return await self._complete_todo_action(
                conversation=conversation,
                project_id=request.project_id,
                title_query=structured_context.get("todo_title_query")
                or request.message,
            )

        if intent == "DOWNLOAD_ARTIFACT":
            return await self._artifact_download_response(
                conversation=conversation,
                project_id=request.project_id,
                structured_context=structured_context,
            )

        return await self._render_and_save_response(
            conversation=conversation,
            project_id=request.project_id,
            result_json={
                "event": "GENERAL_QA",
                "query": request.message,
                "topic": structured_context.get("topic"),
            },
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

    async def _build_input_context(
        self,
        *,
        conversation: ConversationMetadata,
        request: ChatMessageRequest,
    ) -> dict[str, Any]:
        context = dict(request.context or {})
        context.setdefault("current_project_id", request.project_id)
        context.setdefault("project_id", request.project_id)

        if "last_agent_response_summary" not in context:
            latest_assistant_message = await self._latest_assistant_message(
                project_id=request.project_id,
                conversation_id=conversation.conversation_id,
            )
            if latest_assistant_message is not None:
                context["last_agent_response_summary"] = (
                    self._summarize_agent_response(latest_assistant_message)
                )

        if "pending_action" not in context:
            pending_action = await self.conversation_repository.get_latest_waiting_action(
                project_id=request.project_id,
                conversation_id=conversation.conversation_id,
            )
            if pending_action is not None:
                context["pending_action"] = pending_action.model_dump(mode="json")

        if "uploaded_documents" not in context and hasattr(
            self.document_service,
            "list_documents",
        ):
            try:
                documents = await self.document_service.list_documents(
                    project_id=request.project_id,
                )
            except Exception:
                documents = []
            if documents:
                context["uploaded_documents"] = [
                    document.model_dump(mode="json")
                    if hasattr(document, "model_dump")
                    else document
                    for document in documents
                ]

        if "generated_artifacts" not in context and hasattr(
            self.artifact_service,
            "list_artifacts",
        ):
            try:
                artifacts = await self.artifact_service.list_artifacts(
                    project_id=request.project_id,
                )
            except Exception:
                artifacts = []
            if artifacts:
                context["generated_artifacts"] = [
                    artifact.model_dump(mode="json")
                    if hasattr(artifact, "model_dump")
                    else artifact
                    for artifact in artifacts
                ]

        action_item_repository = getattr(
            self.schedule_service,
            "action_item_repository",
            None,
        )
        if "recent_todos" not in context and action_item_repository is not None:
            try:
                todos = await action_item_repository.list_project_todos(
                    project_id=request.project_id,
                )
            except Exception:
                todos = []
            if todos:
                context["recent_todos"] = todos[:10]

        return context

    async def _artifact_download_response(
        self,
        *,
        conversation: ConversationMetadata,
        project_id: str,
        structured_context: dict[str, Any],
    ) -> ChatResponse:
        artifact_ref = structured_context.get("artifact_ref") or {}
        artifact_id = artifact_ref.get("artifact_id") or structured_context.get(
            "artifact_id"
        )
        if not artifact_id:
            return await self._render_and_save_response(
                conversation=conversation,
                project_id=project_id,
                result_json={
                    "event": "ARTIFACT_DOWNLOAD_REQUIRED_INFO",
                    "missing_fields": structured_context.get("missing_slots")
                    or ["artifact_id"],
                    "available_artifacts": structured_context.get(
                        "available_artifacts"
                    )
                    or [],
                },
            )

        artifact = {
            "artifact_id": artifact_id,
            "artifact_type": artifact_ref.get("artifact_type")
            or structured_context.get("artifact_type"),
            "name": artifact_ref.get("name"),
        }
        return await self._render_and_save_response(
            conversation=conversation,
            project_id=project_id,
            result_json={
                "event": "ARTIFACT_DOWNLOAD_READY",
                "artifact": artifact,
                "file_name": artifact_ref.get("file_name"),
            },
        )

    async def _latest_assistant_message(
        self,
        *,
        project_id: str,
        conversation_id: str,
    ) -> Any | None:
        if not hasattr(self.conversation_repository, "get_latest_message_by_role"):
            return None
        try:
            return await self.conversation_repository.get_latest_message_by_role(
                project_id=project_id,
                conversation_id=conversation_id,
                role=ChatRole.ASSISTANT,
            )
        except Exception:
            return None

    def _summarize_agent_response(self, message: Any) -> dict[str, Any]:
        payload = getattr(message, "structured_payload", None) or {}
        content = str(getattr(message, "content", "") or "")
        result = payload.get("result") if isinstance(payload, dict) else None
        summary: dict[str, Any] = {
            "message_id": getattr(message, "message_id", None),
            "content": content[:500],
        }
        if isinstance(payload, dict):
            for key in ("state", "display_type", "message"):
                if payload.get(key):
                    summary[key] = payload.get(key)
        if isinstance(result, dict):
            metadata = result.get("metadata") or {}
            if result.get("action"):
                summary["action"] = result.get("action")
            if result.get("status"):
                summary["status"] = result.get("status")
            if isinstance(metadata, dict) and metadata.get("todo_count") is not None:
                summary["todo_count"] = metadata.get("todo_count")
        return summary

    async def _prepare_generation_action(
        self,
        *,
        conversation: ConversationMetadata,
        request: ChatMessageRequest,
        structured_context: dict[str, Any],
    ) -> ChatResponse:
        target_artifact_type = ArtifactType(structured_context["target_artifact_type"])
        project_start_date = self._project_context_value(request.context, "start_date")
        if target_artifact_type == ArtifactType.WBS and not str(project_start_date or "").strip():
            return await self._render_and_save_response(
                conversation=conversation,
                project_id=request.project_id,
                result_json={
                    "event": "REQUIRED_INFO",
                    "target_artifact_type": target_artifact_type.value,
                    "query": request.message,
                    "missing_fields": ["project_start_date"],
                    "required_project_fields": ["project_start_date"],
                },
            )

        source_document_ids = structured_context.get("source_document_ids") or []
        if not source_document_ids:
            return await self._render_and_save_response(
                conversation=conversation,
                project_id=request.project_id,
                result_json={
                    "event": "REQUIRED_INFO",
                    "target_artifact_type": structured_context.get(
                        "target_artifact_type"
                    ),
                    "query": request.message,
                    "required_source_document_types": structured_context.get(
                        "required_source_document_types"
                    )
                    or [],
                },
            )

        validation_request = GenerationRequest(
            project_id=request.project_id,
            project_name=request.context.get("project_name"),
            source_document_ids=source_document_ids,
            source_document_type=structured_context.get("source_document_type"),
            target_artifact_type=target_artifact_type,
            query=request.message,
            permission_scope=request.permission_scope,
        )
        validation_result = await self.generation_service.validate_source_documents(
            validation_request,
            document_service=self.document_service,
        )
        if not validation_result.success:
            return await self._render_and_save_response(
                conversation=conversation,
                project_id=request.project_id,
                result_json={
                    "event": "ACTION_FAILED",
                    "error": validation_result.message,
                    "result": validation_result.detail or {},
                },
            )

        source_documents = request.context.get("selected_documents") or []
        if source_document_ids and not source_documents:
            source_documents = await self._source_documents_for_ids(
                project_id=request.project_id,
                document_ids=source_document_ids,
            )

        requirements_confirmed = bool(
            (request.context or {}).get("requirements_confirmed")
            or (request.context or {}).get("wbs_requirements_confirmed")
        )
        if target_artifact_type == ArtifactType.WBS and not requirements_confirmed:
            first_source_document = source_documents[0] if source_documents else {}
            return await self._render_and_save_response(
                conversation=conversation,
                project_id=request.project_id,
                result_json={
                    "event": "REQUIRED_INFO",
                    "target_artifact_type": target_artifact_type.value,
                    "query": request.message,
                    "wbs_precheck": {
                        "source_document_id": (
                            first_source_document.get("document_id")
                            if isinstance(first_source_document, dict)
                            else None
                        ),
                        "source_file_name": (
                            first_source_document.get("file_name")
                            if isinstance(first_source_document, dict)
                            else None
                        ),
                        "source_document_type": (
                            first_source_document.get("document_type")
                            if isinstance(first_source_document, dict)
                            else None
                        ),
                        "source_documents": source_documents,
                        "project_start_date": project_start_date,
                        "requirements_confirmed": False,
                        "original_message": request.message,
                    },
                },
            )

        payload = {
            "project_id": request.project_id,
            "target_artifact_type": target_artifact_type.value,
            "source_document_ids": source_document_ids,
            "source_documents": source_documents,
            "context": {
                **(request.context or {}),
                "source_document_ids": source_document_ids,
                "source_documents": source_documents,
                "requirements_confirmed": requirements_confirmed,
            },
            "source_document_type": structured_context.get("source_document_type"),
            "project_name": request.context.get("project_name"),
            "start_date": project_start_date,
            "end_date": self._project_context_value(request.context, "end_date"),
            "project_period": request.context.get("project_period"),
            "query": request.message,
            "permission_scope": request.permission_scope,
            "server_permission_scope": list(
                request.permission_scope or DEFAULT_MVP_SCOPES
            ),
            "large_document_hint": structured_context.get("large_document_hint")
            or {},
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

    async def _source_documents_for_ids(
        self,
        *,
        project_id: str,
        document_ids: list[str],
    ) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        for document_id in document_ids:
            document = await self.document_service.get_document(
                project_id=project_id,
                document_id=document_id,
            )
            if document is None:
                continue
            document_type = (
                document.document_type.value
                if hasattr(document.document_type, "value")
                else str(document.document_type)
            )
            documents.append(
                {
                    "document_id": document.document_id,
                    "file_name": document.file_name,
                    "document_type": document_type,
                    "display_label": self._display_label_for_document_type(
                        document_type
                    ),
                }
            )
        return documents

    def _display_label_for_document_type(self, document_type: str | None) -> str:
        labels = {
            "CONSTRUCTION_REQUIREMENT_DEFINITION": "업로드한 구축요건 정의서",
            "REQUIREMENT_SPEC": "업로드한 요구사항 명세서",
            "MEETING_NOTES": "업로드한 회의록",
            "WBS": "업로드한 WBS",
        }
        return labels.get(str(document_type or ""), "업로드한 문서")

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
                "schedule_action": structured_context.get("schedule_action")
                or "EXTRACT_TODOS_FROM_MEETING",
                "meeting_notes": structured_context.get("meeting_notes")
                or request.message,
                "source_document_ids": structured_context.get("source_document_ids")
                or [],
                "user_id": request.user_id,
                "permission_scope": request.permission_scope,
                "server_permission_scope": list(
                    request.permission_scope or DEFAULT_MVP_SCOPES
                ),
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
                    "event": "NO_PENDING_ACTION",
                    "action": "CONFIRM",
                },
            )

        await self.conversation_repository.update_action_status(
            project_id=project_id,
            action_id=pending_action.action_id,
            status=ChatActionStatus.EXECUTING,
            result_json={
                "status": ChatActionStatus.EXECUTING.value,
                "action_id": pending_action.action_id,
                "job_id": pending_action.action_id,
            },
        )
        if (
            is_generation_action(pending_action.action_type)
            and self._runs_generation_in_background()
        ):
            started_action = await self.conversation_repository.get_action(
                project_id=project_id,
                action_id=pending_action.action_id,
            )
            asyncio.create_task(
                run_generation_action_job(
                    project_id=project_id,
                    action_id=pending_action.action_id,
                )
            )
            return await self._render_and_save_response(
                conversation=conversation,
                project_id=project_id,
                result_json={
                    "event": "ACTION_STARTED",
                    "action_id": pending_action.action_id,
                    "pending_action": (
                        started_action.model_dump(mode="json")
                        if started_action is not None
                        else pending_action.model_dump(mode="json")
                    ),
                },
                pending_action=started_action or pending_action,
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

    def _runs_generation_in_background(self) -> bool:
        return isinstance(self.generation_service, GenerationService)

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
        else:
            return await self._render_and_save_response(
                conversation=conversation,
                project_id=project_id,
                result_json={
                    "event": "NO_PENDING_ACTION",
                    "action": "CANCEL",
                },
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
            if (
                action is None
                or action.conversation_id != conversation_id
                or action.status != ChatActionStatus.WAITING_CONFIRMATION
            ):
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
            ChatActionType.GENERATE_UNITTEST,
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
            context=payload.get("context") or {},
            project_name=payload.get("project_name"),
            source_document_ids=payload.get("source_document_ids") or [],
            source_document_type=payload.get("source_document_type"),
            target_artifact_type=payload["target_artifact_type"],
            template_id=payload.get("template_id"),
            template_version=payload.get("template_version"),
            query=payload.get("query"),
            permission_scope=payload.get("server_permission_scope")
            or list(DEFAULT_MVP_SCOPES),
        )
        try:
            return await self.generation_service.generate_artifact(
                generation_request,
                artifact_service=self.artifact_service,
                retrieval_service=self.retrieval_service,
                template_service=self.template_service,
                document_service=self.document_service,
            )
        except TypeError:
            return await self.generation_service.generate_artifact(
                generation_request,
                artifact_service=self.artifact_service,
                retrieval_service=self.retrieval_service,
                template_service=self.template_service,
            )

    async def _complete_todo_action(
        self,
        *,
        conversation: ConversationMetadata,
        project_id: str,
        title_query: str,
    ) -> ChatResponse:
        response = await self.schedule_service.complete_todo(
            project_id=project_id,
            title_query=title_query,
        )
        return await self._render_and_save_response(
            conversation=conversation,
            project_id=project_id,
            result_json={
                "event": "SCHEDULE_RESULT",
                "result": response.result if isinstance(response.result, dict) else {},
            },
        )

    async def _run_schedule_query(
        self,
        *,
        conversation: ConversationMetadata,
        request: ChatMessageRequest,
        structured_context: dict[str, Any],
    ) -> ChatResponse:
        response = await self.schedule_service.run_query(
            project_id=request.project_id,
            schedule_action=str(structured_context.get("schedule_action") or ""),
            context={
                **request.context,
                "normalized_input": structured_context,
            },
            permission_scope=request.permission_scope,
        )
        return await self._render_and_save_response(
            conversation=conversation,
            project_id=request.project_id,
            result_json={
                "event": "SCHEDULE_RESULT",
                "result": response.result if isinstance(response.result, dict) else {},
            },
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
            permission_scope=payload.get("server_permission_scope")
            or list(DEFAULT_MVP_SCOPES),
        )
        return await self.schedule_service.extract_todos(
            schedule_request,
            structured_context={
                "source": "chat",
                "action_id": action.action_id,
                "schedule_action": payload.get("schedule_action")
                or "EXTRACT_TODOS_FROM_MEETING",
            },
        )

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
            download_files=display_payload.get("download_files") or [],
        )

    def _action_type_for_artifact(self, artifact_type: ArtifactType) -> ChatActionType:
        mapping = {
            ArtifactType.REQUIREMENT_SPEC: ChatActionType.GENERATE_REQUIREMENT,
            ArtifactType.WBS: ChatActionType.GENERATE_WBS,
            ArtifactType.SCREEN_DESIGN: ChatActionType.GENERATE_SCREEN_DESIGN,
            ArtifactType.UNITTEST_SPEC: ChatActionType.GENERATE_UNITTEST,
        }
        return mapping[artifact_type]

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:12].upper()}"

    def _project_context_value(
        self,
        context: dict[str, Any],
        field_name: str,
    ) -> Any:
        value = context.get(field_name)
        if value:
            return value
        project = context.get("project")
        if isinstance(project, dict):
            return project.get(field_name)
        return None
