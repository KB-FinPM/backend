# EN: Orchestrates internal result formatting for user-facing responses.
# KO: 내부 처리 결과를 사용자 응답으로 변환하는 Orchestrator입니다.

from app.agents.output_agents.markdown_agent.agent import (
    MarkdownOutputAgent,
    markdown_output_agent,
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
    ) -> None:
        self.markdown_agent = markdown_agent

    async def format(self, request: OutputAgentRequest) -> OutputAgentResponse:
        if request.response_type == OutputResponseType.API_RESPONSE:
            return OutputAgentResponse(
                success=not request.errors,
                agent_name="OutputOrchestrator",
                message=request.message,
                display_payload=request.result_json,
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


output_orchestrator = OutputOrchestrator()
