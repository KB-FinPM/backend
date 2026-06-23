# EN: Orchestrates user input normalization before domain processing.
# KO: 도메인 처리 전 사용자 입력 표준화를 제어하는 Orchestrator입니다.

from app.agents.input_agents.document_parser_agent.agent import (
    DocumentParserAgent,
    document_parser_agent,
)
from app.agents.input_agents.chat_input_agent.agent import (
    ChatInputAgent,
    chat_input_agent,
)
from app.agents.input_agents.meeting_todo_extraction_agent.agent import (
    MeetingTodoExtractionAgent,
    meeting_todo_extraction_agent,
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
        chat_input: ChatInputAgent = chat_input_agent,
        meeting_todo_extractor: MeetingTodoExtractionAgent = (
            meeting_todo_extraction_agent
        ),
    ) -> None:
        self.document_parser = document_parser
        self.chat_input = chat_input
        self.meeting_todo_extractor = meeting_todo_extractor

    async def normalize(self, request: InputAgentRequest) -> InputAgentResponse:
        if request.input_type == InputType.TEXT:
            return await self.chat_input.parse(request)

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

        if request.input_type == InputType.MEETING_NOTES:
            meeting_notes = request.raw_payload.get("meeting_notes")
            source_document_ids = request.context.get("source_document_ids") or []
            extraction = await self.meeting_todo_extractor.extract(
                project_id=request.project_id,
                meeting_notes=str(meeting_notes or ""),
                permission_scope=request.permission_scope,
                source_document_ids=source_document_ids,
                context=request.context,
            )
            return InputAgentResponse(
                agent_name="InputOrchestrator",
                normalized_request_type=NormalizedRequestType.SCHEDULE_TODO_EXTRACTION,
                structured_context={
                    "raw_payload": request.raw_payload,
                    "context": request.context,
                    "permission_scope": request.permission_scope,
                    "user_id": request.user_id,
                    "meeting_notes": meeting_notes,
                    "source_document_ids": source_document_ids,
                    "meeting_todo_extraction": extraction,
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
