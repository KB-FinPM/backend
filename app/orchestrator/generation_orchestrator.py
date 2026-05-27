from typing import Any

from app.agents.core_agents.requirement_agent.agent import requirement_agent
from app.agents.core_agents.validator_agent.agent import validator_agent
from app.core.logger import get_logger
from app.rag.retrieval import retrieval_service
from app.schemas.agent import AgentRequest, AgentResponse
from app.schemas.request import GenerationRequest
from app.schemas.response import GenerationResponse

logger = get_logger(__name__)


class GenerationOrchestrator:
    """Coordinates generation flows across retrieval, core agents, and validation."""

    def __init__(
        self,
        retrieval: Any = retrieval_service,
        requirement_generator: Any = requirement_agent,
        validator: Any = validator_agent,
    ) -> None:
        self.retrieval = retrieval
        self.requirement_generator = requirement_generator
        self.validator = validator

    async def generate_requirement(self, request: GenerationRequest) -> GenerationResponse:
        generation_flow = request.generation_flow()
        logger.info(
            "[Orchestrator] generate_requirement start | "
            f"project_id={request.project_id} | "
            f"target_artifact_type={generation_flow.target_artifact_type}"
        )

        documents = await self.retrieval.search(
            project_id=request.project_id,
            query=request.query or "",
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
                "template": generation_flow.template.model_dump(),
                "query": request.query,
            },
        )
        agent_response = await self.requirement_generator.generate(agent_request)
        if not agent_response.success:
            return self._failed_response(request, agent_response)

        validated_response = await self.validator.validate(agent_response.result)
        if not validated_response.success:
            return self._failed_response(request, validated_response)

        logger.info(
            "[Orchestrator] generate_requirement done | "
            f"project_id={request.project_id}"
        )
        return GenerationResponse(
            project_id=request.project_id,
            result=validated_response.result,
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
