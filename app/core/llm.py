# EN: LLM service wrapper for Bedrock or future model providers.
# KO: Bedrock 및 향후 모델 제공자를 감싸는 LLM 서비스 래퍼입니다.

import boto3
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class LLMService:
    """
    모든 Agent는 이 클래스를 통해서만 LLM을 호출합니다.
    Agent에서 boto3 또는 Bedrock 직접 호출 금지.
    """

    def __init__(self):
        # TODO: AWS 자격증명 세팅 후 활성화
        # self.client = boto3.client(
        #     "bedrock-runtime",
        #     region_name=settings.AWS_REGION,
        # )
        self.model_id = settings.BEDROCK_MODEL_ID

    async def invoke(self, prompt: str, system: str = "") -> str:
        """
        Bedrock Claude 호출.
        현재는 로컬 개발용 Mock 응답 반환.
        """
        logger.info(f"LLM invoke | model={self.model_id}")
        logger.debug(f"prompt preview: {prompt[:100]}...")

        # TODO: 실제 Bedrock 호출로 교체
        # response = self.client.invoke_model(...)
        return "[LLM Mock 응답] 실제 Bedrock 연동 전 테스트 응답입니다."


llm_service = LLMService()
