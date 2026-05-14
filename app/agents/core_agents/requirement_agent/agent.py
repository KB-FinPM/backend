from app.schemas.agent import AgentRequest, AgentResponse
from app.core.llm import llm_service
from app.core.logger import get_logger

logger = get_logger(__name__)


class RequirementAgent:
    """
    요구사항 생성 전담 Agent.
    역할: 문서 청크 → 요구사항 JSON 생성
    금지: DB 저장, S3 접근, HTTP Response 생성
    """

    AGENT_NAME = "RequirementAgent"

    async def generate(self, request: AgentRequest) -> AgentResponse:
        logger.info(f"[{self.AGENT_NAME}] generate start | project_id={request.project_id}")

        try:
            prompt = self._build_prompt(request)
            llm_result = await llm_service.invoke(prompt)

            # TODO: LLM 결과 JSON 파싱 및 스키마 검증

            logger.info(f"[{self.AGENT_NAME}] generate done")
            return AgentResponse(
                agent_name=self.AGENT_NAME,
                result={"raw": llm_result},
            )

        except Exception as e:
            logger.error(f"[{self.AGENT_NAME}] error: {e}")
            return AgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                error=str(e),
            )

    def _build_prompt(self, request: AgentRequest) -> str:
        # TODO: prompts/requirement_prompt.txt 로드 및 템플릿 적용
        context = "\n".join([str(doc) for doc in request.documents])
        return f"다음 문서를 기반으로 요구사항을 생성하세요:\n\n{context}"


requirement_agent = RequirementAgent()
