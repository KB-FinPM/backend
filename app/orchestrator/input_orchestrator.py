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
        # TODO: Route TEXT, MEETING_NOTES, and ARTIFACT_REQUEST inputs to dedicated
        # input agents once those agents are implemented.
        if request.input_type == InputType.FILE:
            return await self.document_parser.parse(request)

        if request.input_type == InputType.ARTIFACT_REQUEST:
            return InputAgentResponse(
                agent_name="InputOrchestrator",
                normalized_request_type=NormalizedRequestType.ARTIFACT_GENERATION,
                structured_context={
                    "raw_payload": request.raw_payload,
                    "context": request.context,
                    "permission_scope": request.permission_scope,
                    "user_id": request.user_id,
                },
            )

        return InputAgentResponse(
            success=False,
            agent_name="InputOrchestrator",
            normalized_request_type=NormalizedRequestType.UNKNOWN,
            error="unsupported input type",
            validation_errors=["unsupported input type"],
        )


input_orchestrator = InputOrchestrator()
