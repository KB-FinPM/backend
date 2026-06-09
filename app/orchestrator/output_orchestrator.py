# EN: Orchestrates internal result formatting for user-facing responses.
# KO: 내부 처리 결과를 사용자 응답으로 변환하는 Orchestrator입니다.

from app.agents.output_agents.markdown_agent.agent import (
    MarkdownOutputAgent,
    markdown_output_agent,
)
from app.agents.output_agents.chat_agent.agent import (
    ChatOutputAgent,
    chat_output_agent,
)
from app.schemas.io_agent import (
    OutputAgentRequest,
    OutputAgentResponse,
    OutputResponseType,
)


class OutputOrchestrator:
    """Routes internal result JSON to the proper output agent."""

    def __init__(
        self,
        markdown_agent: MarkdownOutputAgent = markdown_output_agent,
        chat_agent: ChatOutputAgent = chat_output_agent,
    ) -> None:
        self.markdown_agent = markdown_agent
        self.chat_agent = chat_agent

    async def format(self, request: OutputAgentRequest) -> OutputAgentResponse:
        if request.response_type == OutputResponseType.CHAT_RESPONSE:
            return await self.chat_agent.render(request)

        if request.response_type == OutputResponseType.API_RESPONSE:
            display_payload = self._format_api_display_payload(request)
            return OutputAgentResponse(
                success=not request.errors,
                agent_name="OutputOrchestrator",
                message=display_payload.get("message", request.message)
                if isinstance(display_payload, dict)
                else request.message,
                display_payload=display_payload,
                artifact_refs=[request.artifact] if request.artifact else [],
                error="; ".join(request.errors) if request.errors else None,
            )

        # TODO: Add DOCX/PDF/XLSX export agents, then persist generated files
        # through the storage service.
        if (
            request.response_type == OutputResponseType.ARTIFACT_EXPORT
            and request.output_format == "markdown"
        ):
            return await self.markdown_agent.render(request)

        return OutputAgentResponse(
            success=False,
            agent_name="OutputOrchestrator",
            message="unsupported output request",
            error="unsupported output request",
        )

    def _format_api_display_payload(
        self,
        request: OutputAgentRequest,
    ) -> dict:
        if request.errors:
            return self.chat_agent.build_display_payload(
                {
                    "event": "ACTION_FAILED",
                    "error": "; ".join(request.errors),
                    "result": request.result_json,
                }
            )

        result = request.result_json.get("result")
        if isinstance(result, dict) and (
            result.get("artifact_type") == "SCHEDULE_TODO_LIST"
            or "todos" in result
            or "artifact" in result
            or "generated" in result
        ):
            return self.chat_agent.build_display_payload(
                {
                    "event": "ACTION_COMPLETED",
                    "result": result,
                }
            )

        return request.result_json


output_orchestrator = OutputOrchestrator()
