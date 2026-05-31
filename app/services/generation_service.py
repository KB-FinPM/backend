# EN: Business service for artifact generation use cases.
# KO: 산출물 생성 유스케이스를 담당하는 비즈니스 서비스입니다.

from typing import Any

from app.orchestrator.generation_orchestrator import GenerationOrchestrator
from app.schemas.request import GenerationRequest
from app.schemas.response import GenerationResponse


class GenerationService:
    """Keeps generation API routes stable while orchestrators evolve."""

    def __init__(self, orchestrator: GenerationOrchestrator) -> None:
        self.orchestrator = orchestrator

    async def generate_requirement(
        self,
        request: GenerationRequest,
        *,
        artifact_service: Any,
        retrieval_service: Any = None,
    ) -> GenerationResponse:
        return await self.orchestrator.generate_requirement(
            request,
            artifact_service=artifact_service,
            retrieval_service=retrieval_service,
        )
