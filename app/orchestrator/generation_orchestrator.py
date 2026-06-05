# EN: Orchestrates source-document based artifact generation flows.
# KO: 선행 문서 기반 후행 산출물 생성 흐름을 제어합니다.

from typing import Any
from uuid import uuid4

from app.agents.core_agents.artifact_agent.agent import ArtifactAgent
from app.agents.core_agents.requirement_agent.agent import requirement_agent
from app.agents.core_agents.screen_design_agent.agent import screen_design_agent
from app.agents.core_agents.validator_agent.agent import validator_agent
from app.agents.core_agents.wbs_agent.agent import wbs_agent
from app.core.logger import get_logger
from app.rag.retrieval import retrieval_service
from app.schemas.agent import AgentRequest, AgentResponse
from app.schemas.artifact import ArtifactType
from app.schemas.request import GenerationRequest
from app.schemas.response import GenerationResponse

logger = get_logger(__name__)


class GenerationOrchestrator:
    """Coordinates generation flows across retrieval, core agents, and validation."""

    def __init__(
        self,
        retrieval: Any = retrieval_service,
        artifact_generator: Any = None,
        requirement_generator: Any = requirement_agent,
        wbs_generator: Any = wbs_agent,
        screen_design_generator: Any = screen_design_agent,
        validator: Any = validator_agent,
    ) -> None:
        self.retrieval = retrieval
        self.artifact_generator = artifact_generator or ArtifactAgent(
            requirement_generator=requirement_generator,
            wbs_generator=wbs_generator,
            screen_design_generator=screen_design_generator,
        )
        self.validator = validator

    async def generate_requirement(
        self,
        request: GenerationRequest,
        artifact_service: Any = None,
        retrieval_service: Any = None,
        template_service: Any = None,
    ) -> GenerationResponse:
        return await self.generate_artifact(
            request,
            artifact_service=artifact_service,
            retrieval_service=retrieval_service,
            template_service=template_service,
        )

    async def generate_artifact(
        self,
        request: GenerationRequest,
        artifact_service: Any = None,
        retrieval_service: Any = None,
        template_service: Any = None,
    ) -> GenerationResponse:
        generation_flow = request.generation_flow()
        if generation_flow.target_artifact_type in {
            ArtifactType.REQUIREMENT_SPEC,
            ArtifactType.WBS,
            ArtifactType.SCREEN_DESIGN,
        }:
            return await self._generate_agent_artifact(
                request,
                generator=self.artifact_generator,
                artifact_service=artifact_service,
                retrieval_service=retrieval_service,
                template_service=template_service,
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
    ) -> GenerationResponse:
        generation_flow = request.generation_flow()
        logger.info(
            "[Orchestrator] generate_artifact start | "
            f"project_id={request.project_id} | "
            f"target_artifact_type={generation_flow.target_artifact_type}"
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
        documents = await retrieval.search(
            project_id=request.project_id,
            permission_scope=request.permission_scope,
            query=request.query or "",
            document_ids=request.source_document_ids or None,
        )

        agent_request = AgentRequest(
            project_id=request.project_id,
            documents=documents,
            context={
                "source_document_ids": request.source_document_ids,
                "document_ids": request.document_ids,
                "source_document_type": (
                    generation_flow.source_document_type.value
                    if generation_flow.source_document_type
                    else None
                ),
                "target_artifact_type": generation_flow.target_artifact_type.value,
                "template": template_context,
                "query": request.query,
                "permission_scope": request.permission_scope,
            },
        )
        agent_response = await generator.generate(agent_request)
        if not agent_response.success:
            return self._failed_response(request, agent_response)

        validated_response = await self.validator.validate(agent_response.result)
        if not validated_response.success:
            return self._failed_response(request, validated_response)

        if artifact_service is not None:
            artifact = await artifact_service.create_artifact(
                artifact_id=f"ART-{uuid4().hex[:12].upper()}",
                project_id=request.project_id,
                artifact_type=generation_flow.target_artifact_type,
                name=generation_flow.target_artifact_type.value,
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
            )
            result = {
                "artifact": artifact.model_dump(mode="json"),
                "generated": validated_response.result,
            }
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
