# EN: Orchestrates source-document based artifact generation flows.
# KO: 선행 문서 기반 후행 산출물 생성 흐름을 제어합니다.

from typing import Any
from uuid import uuid4

from app.agents.core_agents.artifact_agent.agent import ArtifactAgent
from app.agents.core_agents.requirement_agent.agent import requirement_agent
from app.agents.core_agents.screen_design_agent.agent import screen_design_agent
from app.agents.core_agents.unit_test_agent.agent import unit_test_agent
from app.agents.core_agents.validator_agent.agent import validator_agent
from app.agents.core_agents.wbs_agent.agent import wbs_agent
from app.core.config import settings
from app.core.llm import llm_service
from app.core.logger import get_logger
from app.rag.retrieval import retrieval_service
from app.schemas.agent import AgentRequest, AgentResponse
from app.schemas.artifact import ArtifactType
from app.services.artifact_export_service import artifact_export_service
from app.schemas.request import GenerationRequest
from app.schemas.response import GenerationResponse
from util.agent_generation_utils import extract_requirement_atoms_from_pipe_tables

logger = get_logger(__name__)
LLM_LOG_PREFIX = "!!! LLM"


class GenerationOrchestrator:
    """Coordinates generation flows across retrieval, core agents, and validation."""

    def __init__(
        self,
        retrieval: Any = retrieval_service,
        artifact_generator: Any = None,
        requirement_generator: Any = requirement_agent,
        wbs_generator: Any = wbs_agent,
        screen_design_generator: Any = screen_design_agent,
        unit_test_generator: Any = unit_test_agent,
        validator: Any = validator_agent,
    ) -> None:
        self.retrieval = retrieval
        self.artifact_generator = artifact_generator or ArtifactAgent(
            requirement_generator=requirement_generator,
            wbs_generator=wbs_generator,
            screen_design_generator=screen_design_generator,
            unit_test_generator=unit_test_generator,
        )
        self.validator = validator

    async def generate_requirement(
        self,
        request: GenerationRequest,
        artifact_service: Any = None,
        retrieval_service: Any = None,
        template_service: Any = None,
        document_service: Any = None,
    ) -> GenerationResponse:
        return await self.generate_artifact(
            request,
            artifact_service=artifact_service,
            retrieval_service=retrieval_service,
            template_service=template_service,
            document_service=document_service,
        )

    async def generate_artifact(
        self,
        request: GenerationRequest,
        artifact_service: Any = None,
        retrieval_service: Any = None,
        template_service: Any = None,
        document_service: Any = None,
    ) -> GenerationResponse:
        generation_flow = request.generation_flow()
        logger.info(
            "[Orchestrator] dispatch | "
            f"project_id={request.project_id} | "
            f"target_artifact_type={generation_flow.target_artifact_type} | "
            f"source_document_type={generation_flow.source_document_type or 'UNKNOWN'}"
        )
        if generation_flow.target_artifact_type in {
            ArtifactType.REQUIREMENT_SPEC,
            ArtifactType.UNITTEST_SPEC,
            ArtifactType.WBS,
            ArtifactType.SCREEN_DESIGN,
        }:
            return await self._generate_agent_artifact(
                request,
                generator=self.artifact_generator,
                artifact_service=artifact_service,
                retrieval_service=retrieval_service,
                template_service=template_service,
                document_service=document_service,
            )

        # TODO: Wire Action Items agent into this dispatch table when it becomes
        # part of the active product scope.
        return self._not_implemented_response(
            request,
            generation_flow.target_artifact_type,
        )

    async def _generate_agent_artifact(
        self,
        request: GenerationRequest,
        generator: Any,
        artifact_service: Any = None,
        retrieval_service: Any = None,
        template_service: Any = None,
        document_service: Any = None,
    ) -> GenerationResponse:
        generation_flow = request.generation_flow()
        logger.info(
            "[Orchestrator] generate_artifact start | "
            f"project_id={request.project_id} | "
            f"target_artifact_type={generation_flow.target_artifact_type} | "
            f"source_document_ids={request.source_document_ids or []}"
        )

        resolved_template = None
        if template_service is not None:
            resolved_template = await template_service.resolve_template(
                reference=generation_flow.template,
                artifact_type=generation_flow.target_artifact_type,
            )
            if generation_flow.template.template_id and resolved_template is None:
                return self._failed_response(
                    request,
                    AgentResponse(
                        success=False,
                        agent_name="TemplateService",
                        error="template not found",
                    ),
                )

        template_context = (
            resolved_template.model_dump(mode="json")
            if resolved_template is not None
            else generation_flow.template.model_dump(mode="json")
        )

        retrieval = retrieval_service or self.retrieval
        # For artifact generation, especially requirement extraction, load all
        # chunks from the selected source document. Passing user-facing commands
        # like "요구사항명세서를 생성해줘" as keyword filters can reduce context
        # to one irrelevant chunk and degrade output quality.
        retrieval_query = ""
        top_k = min(
            max(settings.GENERATION_RETRIEVAL_TOP_K, 1),
            max(settings.GENERATION_MAX_SOURCE_CHUNKS, 1),
        )
        documents = await retrieval.search(
            project_id=request.project_id,
            permission_scope=request.permission_scope,
            query=retrieval_query,
            top_k=top_k,
            document_ids=request.source_document_ids or None,
            search_mode="text",
        )

        agent_request = AgentRequest(
            project_id=request.project_id,
            documents=documents,
            context={
                "source_document_ids": request.source_document_ids,
                "document_ids": request.document_ids,
                "project_name": request.project_name,
                "start_date": request.start_date,
                "project_period": request.project_period,
                "source_document_type": (
                    generation_flow.source_document_type.value
                    if generation_flow.source_document_type
                    else None
                ),
                "target_artifact_type": generation_flow.target_artifact_type.value,
                "project_name": request.project_name or request.project_id,
                "template": template_context,
                "query": request.query,
                "author": request.author_value(),
                "writer": request.writer,
                "created_by": request.created_by,
                "user_id": request.user_id,
                "permission_scope": request.permission_scope,
                "generation_orchestrator": self,
            },
        )
        agent_response = await generator.generate(agent_request)
        if not agent_response.success:
            return self._failed_response(request, agent_response)

        validated_response = await self.validator.validate(agent_response.result)
        if not validated_response.success:
            return self._failed_response(request, validated_response)

        if artifact_service is not None:
            artifact_id = f"ART-{uuid4().hex[:12].upper()}"
            export_result = await artifact_export_service.export_artifact(
                project_id=request.project_id,
                artifact_id=artifact_id,
                artifact_type=generation_flow.target_artifact_type,
                result_json=validated_response.result,
                project_name=request.project_name,
                document_service=document_service,
                storage_service=(
                    document_service.storage_service
                    if document_service is not None
                    else None
                ),
            )
            storage_path = export_result.storage_path if export_result else None
            artifact = await artifact_service.create_artifact(
                artifact_id=artifact_id,
                project_id=request.project_id,
                artifact_type=generation_flow.target_artifact_type,
                name=(
                    export_result.file_name
                    if export_result is not None
                    else generation_flow.target_artifact_type.value
                ),
                source_document_ids=request.source_document_ids,
                template_id=(
                    resolved_template.template_id
                    if resolved_template is not None
                    else generation_flow.template.template_id
                ),
                template_version=(
                    resolved_template.template_version
                    if resolved_template is not None
                    else generation_flow.template.template_version
                ),
                result_json=validated_response.result,
                storage_path=storage_path,
            )
            result = {
                "artifact": artifact.model_dump(mode="json"),
                "generated": validated_response.result,
            }
            if export_result is not None:
                result["exported_file"] = {
                    "file_name": export_result.file_name,
                    "content_type": export_result.content_type,
                    "storage_path": export_result.storage_path,
                }
                if export_result.document is not None:
                    result["exported_document"] = export_result.document.model_dump(mode="json")
        else:
            result = validated_response.result

        logger.info(
            "[Orchestrator] generate_artifact done | "
            f"project_id={request.project_id}"
        )
        return GenerationResponse(
            project_id=request.project_id,
            message="artifact generated" if artifact_service is not None else "ok",
            result=result,
        )


    async def invoke_agent_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        call_index: int | None = None,
        call_total: int | None = None,
        call_label: str | None = None,
    ) -> str:
        """Delegates agent LLM execution through the orchestrator boundary.

        Core agents must not instantiate Bedrock or other model clients directly.
        The current backend LLM service accepts a single prompt, so the system
        and user prompts are composed here.
        """
        prompt = (
            f"System instruction:\n{system_prompt.strip()}\n\n"
            f"User input:\n{user_prompt.strip()}"
        )
        logger.info(
            f"[Orchestrator] {LLM_LOG_PREFIX} invoke request | "
            f"system_chars={len(system_prompt)} | user_chars={len(user_prompt)}"
        )
        logger.debug(
            f"[Orchestrator] {LLM_LOG_PREFIX} prompt preview | "
            f"text={prompt[:300]}"
        )
        response = await llm_service.invoke(
            prompt,
            call_index=call_index,
            call_total=call_total,
            call_label=call_label,
        )
        logger.info(
            f"[Orchestrator] {LLM_LOG_PREFIX} invoke response | "
            f"response_chars={len(response)} | "
            f"progress={(f'{call_index}/{call_total}' if call_total is not None and call_index is not None else 'n/a')}"
        )
        logger.debug(
            f"[Orchestrator] {LLM_LOG_PREFIX} response preview | "
            f"text={response[:300]}"
        )
        return response

    def extract_requirement_atoms_from_pipe_tables(
        self,
        documents: list[dict],
    ) -> list[dict]:
        """Expose table extraction through the orchestrator boundary."""
        return extract_requirement_atoms_from_pipe_tables(documents)

    async def search_agent_context(
        self,
        project_id: str,
        permission_scope: list[str],
        query: str = "",
        document_ids: list[str] | None = None,
        retrieval_service: Any = None,
    ) -> list[dict]:
        """Delegates RAG/vector lookup through the orchestrator boundary."""
        retrieval = retrieval_service or self.retrieval
        return await retrieval.search(
            project_id=project_id,
            permission_scope=permission_scope,
            query=query,
            document_ids=document_ids,
            search_mode="vector",
        )

    def _not_implemented_response(
        self,
        request: GenerationRequest,
        artifact_type: ArtifactType,
    ) -> GenerationResponse:
        message = f"{artifact_type.value} generation is not implemented yet"
        logger.warning(
            "[Orchestrator] generation not implemented | "
            f"project_id={request.project_id} | artifact_type={artifact_type.value}"
        )
        return GenerationResponse(
            success=False,
            message=message,
            project_id=request.project_id,
            result={
                "artifact_type": artifact_type.value,
                "error": message,
            },
        )

    def _failed_response(
        self,
        request: GenerationRequest,
        agent_response: AgentResponse,
    ) -> GenerationResponse:
        logger.warning(
            "[Orchestrator] generate_requirement failed | "
            f"project_id={request.project_id} | "
            f"agent={agent_response.agent_name} | error={agent_response.error}"
        )
        return GenerationResponse(
            success=False,
            message=agent_response.error or "generation failed",
            project_id=request.project_id,
            result={
                "agent_name": agent_response.agent_name,
                "error": agent_response.error,
            },
        )


generation_orchestrator = GenerationOrchestrator()
