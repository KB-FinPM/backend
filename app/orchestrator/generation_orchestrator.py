# EN: Orchestrates source-document based artifact generation flows.
# KO: 선행 문서 기반 후행 산출물 생성 흐름을 제어합니다.

import inspect
from typing import Any
from time import perf_counter
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
from app.schemas.progress import build_generation_progress, build_progress_segment
from app.services.artifact_export_service import artifact_export_service
from app.schemas.request import GenerationRequest
from app.schemas.response import GenerationResponse
from util.agent_generation_utils import extract_requirement_atoms_from_pipe_tables

logger = get_logger(__name__)
LLM_LOG_PREFIX = "!!! LLM"


class AgentRuntimeInvoker:
    """Per-request runtime boundary exposed to core agents."""

    def __init__(
        self,
        *,
        llm=llm_service,
        progress_reporter: Any = None,
        stage: str = "CORE_AGENT_EXTRACTION",
        stage_label: str = "Core Agent 요구사항 추출 중",
        stage_progress: int = 45,
        stage_progress_text: str = "요구사항 추출 중",
    ) -> None:
        self.llm = llm
        self.progress_reporter = progress_reporter
        self.stage = stage
        self.stage_label = stage_label
        self.stage_progress = stage_progress
        self.stage_progress_text = stage_progress_text

    async def invoke_agent_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        call_index: int | None = None,
        call_total: int | None = None,
        call_label: str | None = None,
    ) -> str:
        progress_text = (
            f"{call_index}/{call_total}"
            if call_index is not None and call_total is not None
            else "n/a"
        )
        logger.info(
            f"[Orchestrator] {LLM_LOG_PREFIX} invoke request | "
            f"label={call_label or 'n/a'} | progress={progress_text} | "
            f"system_chars={len(system_prompt)} | user_chars={len(user_prompt)}"
        )
        logger.debug(
            f"[Orchestrator] {LLM_LOG_PREFIX} user prompt preview | "
            f"text={user_prompt[:300]}"
        )
        response = await self.llm.invoke(
            user_prompt,
            system=system_prompt,
            call_index=call_index,
            call_total=call_total,
            call_label=call_label,
        )
        logger.info(
            f"[Orchestrator] {LLM_LOG_PREFIX} invoke response | "
            f"label={call_label or 'n/a'} | progress={progress_text} | "
            f"response_chars={len(response)}"
        )
        logger.debug(
            f"[Orchestrator] {LLM_LOG_PREFIX} response preview | "
            f"text={response[:300]}"
        )
        await self._report_progress(
            current=call_index,
            total=call_total,
            label=call_label,
        )
        return response

    def extract_requirement_atoms_from_pipe_tables(
        self,
        documents: list[dict],
    ) -> list[dict]:
        return extract_requirement_atoms_from_pipe_tables(documents)

    async def _report_progress(
        self,
        *,
        current: int | None,
        total: int | None,
        label: str | None,
    ) -> None:
        if self.progress_reporter is None:
            return
        current_value = int(current or 0)
        total_value = int(total or 0)
        batch_progress = build_progress_segment(
            progress_type="LLM_BATCH",
            label=label or "LLM batch 처리",
            current=current_value,
            total=total_value,
            unit="batches",
        )
        payload = build_generation_progress(
            stage=self.stage,
            stage_label=self.stage_label,
            progress=self.stage_progress,
            progress_text=self.stage_progress_text,
            batch_progress=batch_progress,
        )
        result = self.progress_reporter(payload)
        if inspect.isawaitable(result):
            await result


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
        progress_reporter: Any = None,
    ) -> GenerationResponse:
        return await self.generate_artifact(
            request,
            artifact_service=artifact_service,
            retrieval_service=retrieval_service,
            template_service=template_service,
            document_service=document_service,
            progress_reporter=progress_reporter,
        )

    async def generate_artifact(
        self,
        request: GenerationRequest,
        artifact_service: Any = None,
        retrieval_service: Any = None,
        template_service: Any = None,
        document_service: Any = None,
        progress_reporter: Any = None,
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
                progress_reporter=progress_reporter,
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
        progress_reporter: Any = None,
    ) -> GenerationResponse:
        started_at = perf_counter()
        generation_flow = request.generation_flow()
        request_context = dict(request.context or {})
        progress_reporter = progress_reporter or request_context.pop(
            "generation_progress_reporter",
            None,
        )
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
        retrieval_top_k = (
            settings.GENERATION_REQUIREMENT_RETRIEVAL_TOP_K
            if generation_flow.target_artifact_type == ArtifactType.REQUIREMENT_SPEC
            else settings.GENERATION_RETRIEVAL_TOP_K
        )
        top_k = min(
            max(retrieval_top_k, 1),
            max(settings.GENERATION_MAX_SOURCE_CHUNKS, 1),
        )
        logger.info(
            "[Orchestrator] retrieval window | "
            f"project_id={request.project_id} | "
            f"target_artifact_type={generation_flow.target_artifact_type} | "
            f"top_k={top_k}"
        )
        await self._emit_progress(
            progress_reporter,
            build_generation_progress(
                stage="INPUT_AGENT_DOCUMENT_ANALYSIS",
                stage_label="Input Agent 문서 분석 중",
                progress=25,
                progress_text="원본 문서 검색 중",
            ),
        )
        retrieval_started_at = perf_counter()
        if request.source_document_ids:
            documents = await retrieval.search(
                project_id=request.project_id,
                permission_scope=request.permission_scope,
                query=retrieval_query,
                top_k=top_k,
                document_ids=request.source_document_ids,
                search_mode="text",
            )
        else:
            documents = []
        logger.info(
            "[Orchestrator] retrieval done | "
            f"project_id={request.project_id} | "
            f"document_count={len(documents)} | "
            f"duration_ms={int((perf_counter() - retrieval_started_at) * 1000)}"
        )
        if request.source_document_ids and not documents:
            return self._failed_response(
                request,
                AgentResponse(
                    success=False,
                    agent_name="RetrievalService",
                    error="source document context not found",
                ),
            )

        chunk_total = len(documents)
        await self._emit_progress(
            progress_reporter,
            build_generation_progress(
                stage="CORE_AGENT_EXTRACTION",
                stage_label="Core Agent 요구사항 추출 중",
                progress=45,
                progress_text="요구사항 추출 중",
                sub_progress=build_progress_segment(
                    progress_type="SOURCE_CHUNK_PROCESSING",
                    label="원본 문서 chunk 처리",
                    current=chunk_total,
                    total=chunk_total,
                    unit="chunks",
                ),
            ),
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
                **request_context,
            },
        )
        agent_started_at = perf_counter()
        runtime_generator = self._generator_with_runtime(
            generator,
            AgentRuntimeInvoker(
                progress_reporter=progress_reporter,
                stage="CORE_AGENT_EXTRACTION",
                stage_label="Core Agent 요구사항 추출 중",
                stage_progress=45,
                stage_progress_text="요구사항 추출 중",
            ),
        )
        agent_response = await runtime_generator.generate(agent_request)
        logger.info(
            "[Orchestrator] agent generation done | "
            f"project_id={request.project_id} | "
            f"target_artifact_type={generation_flow.target_artifact_type} | "
            f"duration_ms={int((perf_counter() - agent_started_at) * 1000)}"
        )
        if not agent_response.success:
            return self._failed_response(request, agent_response)

        await self._emit_progress(
            progress_reporter,
            build_generation_progress(
                stage="VALIDATION_AGENT_CHECK",
                stage_label="Validation Agent 검증 중",
                progress=70,
                progress_text="산출물 검증 중",
            ),
        )
        validated_response = await self._validate_agent_result(
            agent_response.result,
            expected_artifact_type=generation_flow.target_artifact_type,
        )
        if not validated_response.success:
            return self._failed_response(request, validated_response)

        if artifact_service is not None:
            artifact_id = f"ART-{uuid4().hex[:12].upper()}"
            await self._emit_progress(
                progress_reporter,
                build_generation_progress(
                    stage="OUTPUT_AGENT_EXPORT",
                    stage_label="Output Agent 산출물 작성 중",
                    progress=85,
                    progress_text="산출물 파일 작성 중",
                ),
            )
            try:
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
            except (RuntimeError, ValueError, OSError) as exc:
                error_message = f"ArtifactExportService failed: {exc}"
                return self._failed_response(
                    request,
                    AgentResponse(
                        success=False,
                        agent_name="ArtifactExportService",
                        error=error_message,
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
            f"project_id={request.project_id} | "
            f"duration_ms={int((perf_counter() - started_at) * 1000)}"
        )
        await self._emit_progress(
            progress_reporter,
            build_generation_progress(
                stage="DOCUMENT_GENERATION_COMPLETED",
                stage_label="문서 생성 완료",
                progress=100,
                progress_text="문서 생성 완료",
            ),
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
        """Delegates agent LLM execution through the orchestrator boundary."""
        return await AgentRuntimeInvoker().invoke_agent_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            call_index=call_index,
            call_total=call_total,
            call_label=call_label,
        )

    def extract_requirement_atoms_from_pipe_tables(
        self,
        documents: list[dict],
    ) -> list[dict]:
        """Expose table extraction through the orchestrator boundary."""
        return extract_requirement_atoms_from_pipe_tables(documents)

    def _generator_with_runtime(self, generator: Any, runtime: AgentRuntimeInvoker):
        if hasattr(generator, "with_model_invoker"):
            return generator.with_model_invoker(runtime)
        return generator

    async def _emit_progress(
        self,
        progress_reporter: Any,
        payload: dict[str, Any],
    ) -> None:
        if progress_reporter is None:
            return
        result = progress_reporter(payload)
        if inspect.isawaitable(result):
            await result

    async def _validate_agent_result(
        self,
        result: Any,
        *,
        expected_artifact_type: ArtifactType,
    ) -> AgentResponse:
        try:
            return await self.validator.validate(
                result,
                expected_artifact_type=expected_artifact_type,
            )
        except TypeError:
            return await self.validator.validate(result)

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
