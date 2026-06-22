from typing import Any

from app.core.auth import DEFAULT_MVP_SCOPES
from app.core.logger import get_logger
from app.db.session import AsyncSessionLocal
from app.orchestrator.generation_orchestrator import generation_orchestrator
from app.repositories.artifact_repository import ArtifactRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.template_repository import TemplateRepository
from app.rag.retrieval import RetrievalService
from app.schemas.chat import ChatActionMetadata, ChatActionStatus, ChatActionType
from app.schemas.progress import build_generation_progress, normalize_generation_progress
from app.schemas.request import GenerationRequest
from app.schemas.response import GenerationResponse
from app.services.artifact_service import ArtifactService
from app.services.document_service import DocumentService
from app.services.generation_service import GenerationService
from app.services.template_service import TemplateService
from app.storage.s3 import s3_service

logger = get_logger(__name__)

GENERATION_ACTION_TYPES = {
    ChatActionType.GENERATE_REQUIREMENT,
    ChatActionType.GENERATE_WBS,
    ChatActionType.GENERATE_SCREEN_DESIGN,
    ChatActionType.GENERATE_UNITTEST,
}


def is_generation_action(action_type: ChatActionType) -> bool:
    return action_type in GENERATION_ACTION_TYPES


async def run_generation_action_job(*, project_id: str, action_id: str) -> None:
    async with AsyncSessionLocal() as session:
        conversation_repository = ConversationRepository(session)
        action = await conversation_repository.get_action(
            project_id=project_id,
            action_id=action_id,
        )
        if action is None:
            logger.warning(
                "generation job skipped; action not found | "
                f"project_id={project_id} | action_id={action_id}"
            )
            return

        if not is_generation_action(action.action_type):
            logger.warning(
                "generation job skipped; action type is not generation | "
                f"project_id={project_id} | action_id={action_id} | "
                f"action_type={action.action_type}"
            )
            return

        try:
            logger.info(
                "generation job start | "
                f"project_id={project_id} | action_id={action_id}"
            )
            response = await _execute_generation_action(
                action,
                conversation_repository=conversation_repository,
            )
            current_action = await conversation_repository.get_action(
                project_id=project_id,
                action_id=action_id,
            )
            await conversation_repository.update_action_status(
                project_id=project_id,
                action_id=action_id,
                status=ChatActionStatus.EXECUTED
                if response.success
                else ChatActionStatus.FAILED,
                result_json=_response_payload_with_preserved_progress(
                    response,
                    (current_action or action).result_json,
                ),
            )
            logger.info(
                "generation job done | "
                f"project_id={project_id} | action_id={action_id} | "
                f"success={response.success}"
            )
        except Exception as exc:
            logger.exception(
                "generation job failed | "
                f"project_id={project_id} | action_id={action_id}"
            )
            response = GenerationResponse(
                success=False,
                message=str(exc),
                project_id=project_id,
                result={"error": str(exc), "action_id": action_id},
            )
            current_action = await conversation_repository.get_action(
                project_id=project_id,
                action_id=action_id,
            )
            await conversation_repository.update_action_status(
                project_id=project_id,
                action_id=action_id,
                status=ChatActionStatus.FAILED,
                result_json=_response_payload_with_preserved_progress(
                    response,
                    (current_action or action).result_json,
                ),
            )


async def _execute_generation_action(
    action: ChatActionMetadata,
    *,
    conversation_repository: ConversationRepository,
) -> GenerationResponse:
    async with AsyncSessionLocal() as session:
        document_repository = DocumentRepository(session)
        artifact_repository = ArtifactRepository(session)
        template_repository = TemplateRepository(session)

        document_service = DocumentService(document_repository, s3_service)
        artifact_service = ArtifactService(artifact_repository)
        retrieval_service = RetrievalService(document_repository)
        template_service = TemplateService(template_repository)
        generation_service = GenerationService(generation_orchestrator)

        payload = action.payload
        generation_request = GenerationRequest(
            project_id=payload["project_id"],
            context=payload.get("context") or {},
            project_name=payload.get("project_name"),
            start_date=payload.get("start_date"),
            project_period=payload.get("project_period"),
            source_document_ids=payload.get("source_document_ids") or [],
            source_document_type=payload.get("source_document_type"),
            target_artifact_type=payload["target_artifact_type"],
            output_format=payload.get("output_format"),
            template_id=payload.get("template_id"),
            template_version=payload.get("template_version"),
            query=payload.get("query"),
            permission_scope=payload.get("server_permission_scope")
            or list(DEFAULT_MVP_SCOPES),
        )

        async def _report_progress(progress: dict[str, object]) -> None:
            current_action = await conversation_repository.get_action(
                project_id=action.project_id,
                action_id=action.action_id,
            )
            current_result = dict((current_action or action).result_json or {})
            current_result["generation_progress"] = normalize_generation_progress(
                progress,
            )
            await conversation_repository.update_action_status(
                project_id=action.project_id,
                action_id=action.action_id,
                status=ChatActionStatus.EXECUTING,
                result_json=current_result,
            )

        generation_request.context = {
            **(generation_request.context or {}),
            "action_id": action.action_id,
        }

        await conversation_repository.update_action_status(
            project_id=action.project_id,
            action_id=action.action_id,
            status=ChatActionStatus.EXECUTING,
            result_json={
                "action_id": action.action_id,
                "status": ChatActionStatus.EXECUTING.value,
                "generation_progress": build_generation_progress(
                    stage="REQUEST_CONFIRMED",
                    stage_label="요청 확인 중",
                    progress=5,
                    progress_text="요청 확인 중",
                ),
            },
        )
        return await generation_service.generate_artifact(
            generation_request,
            artifact_service=artifact_service,
            retrieval_service=retrieval_service,
            template_service=template_service,
            document_service=document_service,
            progress_reporter=_report_progress,
        )


def _extract_generation_progress(
    result_json: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(result_json, dict):
        return None

    progress = result_json.get("generation_progress")
    if isinstance(progress, dict):
        return progress

    nested_result = result_json.get("result")
    if isinstance(nested_result, dict):
        progress = nested_result.get("generation_progress")
        if isinstance(progress, dict):
            return progress

    return None


def _response_payload_with_preserved_progress(
    response: GenerationResponse,
    previous_result_json: dict[str, Any] | None,
) -> dict[str, Any]:
    final_result = response.model_dump(mode="json")
    previous_progress = _extract_generation_progress(previous_result_json)
    if (
        previous_progress is None
        or _extract_generation_progress(final_result) is not None
    ):
        return final_result

    final_result["generation_progress"] = previous_progress
    nested_result = final_result.get("result")
    if isinstance(nested_result, dict):
        nested_result.setdefault("generation_progress", previous_progress)
    return final_result
