from app.schemas.request import GenerationRequest
from app.schemas.response import GenerationResponse
from app.schemas.agent import AgentRequest
from app.core.logger import get_logger

logger = get_logger(__name__)


class GenerationOrchestrator:
    """
    요구사항 생성 전체 흐름 제어.
    Agent 호출 순서, RAG 검색, Validator 호출을 담당합니다.
    비즈니스 로직이 아닌 흐름(Flow) 만 제어합니다.
    """

    async def generate_requirement(self, request: GenerationRequest) -> GenerationResponse:
        logger.info(f"[Orchestrator] generate_requirement start | project_id={request.project_id}")

        # Step 1. 문서 검색 (RAG)
        # TODO: rag_service.search(project_id, query) 호출
        documents = []

        # Step 2. Input Agent - 문서 정제
        # TODO: document_input_agent.process(documents)

        # Step 3. Core Agent - 요구사항 생성
        agent_request = AgentRequest(
            project_id=request.project_id,
            documents=documents,
        )
        # TODO: requirement_agent.generate(agent_request)
        agent_result = {"mock": "RequirementAgent 결과"}

        # Step 4. Validator Agent
        # TODO: validator_agent.validate(agent_result)

        # Step 5. Output Agent - 결과 포맷팅
        # TODO: document_output_agent.format(agent_result)

        logger.info(f"[Orchestrator] generate_requirement done | project_id={request.project_id}")

        return GenerationResponse(
            project_id=request.project_id,
            result=agent_result,
        )


generation_orchestrator = GenerationOrchestrator()
