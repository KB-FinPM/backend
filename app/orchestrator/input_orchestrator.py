# EN: Orchestrates user input normalization before domain processing.
# KO: 도메인 처리 전 사용자 입력 표준화를 제어하는 Orchestrator입니다.

from app.agents.input_agents.document_parser_agent.agent import (
    DocumentParserAgent,
    document_parser_agent,
)
from app.schemas.io_agent import (
    InputAgentRequest,
    InputAgentResponse,
    InputType,
    NormalizedRequestType,
)


class InputOrchestrator:
    """Routes raw user input to the proper input agent and returns standard JSON."""

    def __init__(
        self,
        document_parser: DocumentParserAgent = document_parser_agent,
    ) -> None:
        self.document_parser = document_parser

    async def normalize(self, request: InputAgentRequest) -> InputAgentResponse:
        if request.input_type == InputType.FILE:
            return await self.document_parser.parse(request)

        return InputAgentResponse(
            success=False,
            agent_name="InputOrchestrator",
            normalized_request_type=NormalizedRequestType.UNKNOWN,
            error="unsupported input type",
            validation_errors=["unsupported input type"],
        )


input_orchestrator = InputOrchestrator()
