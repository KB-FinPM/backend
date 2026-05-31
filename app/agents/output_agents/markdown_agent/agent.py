# EN: Output agent for rendering structured artifacts as Markdown.
# KO: 구조화된 산출물을 Markdown으로 렌더링하는 Output Agent입니다.

from typing import Any

from app.schemas.io_agent import (
    OutputAgentRequest,
    OutputAgentResponse,
    OutputResponseType,
)


class MarkdownOutputAgent:
    """Converts generated artifact JSON into a Markdown document payload."""

    AGENT_NAME = "MarkdownOutputAgent"

    async def render(self, request: OutputAgentRequest) -> OutputAgentResponse:
        if request.response_type != OutputResponseType.ARTIFACT_EXPORT:
            return OutputAgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                message="unsupported response type",
                error="unsupported response type",
            )

        if request.output_format != "markdown":
            return OutputAgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                message="unsupported output format",
                error="unsupported output format",
            )

        markdown = self._render_markdown(request.result_json)
        return OutputAgentResponse(
            agent_name=self.AGENT_NAME,
            message=request.message,
            display_payload={
                "format": "markdown",
                "content": markdown,
            },
            download_files=[],
            artifact_refs=[request.artifact] if request.artifact else [],
        )

    def _render_markdown(self, result_json: dict[str, Any]) -> str:
        artifact_type = result_json.get("artifact_type", "ARTIFACT")
        lines = [f"# {artifact_type}", ""]

        requirements = result_json.get("requirements")
        if isinstance(requirements, list):
            for requirement in requirements:
                if not isinstance(requirement, dict):
                    continue
                title = requirement.get("title") or requirement.get("requirement_id")
                lines.append(f"## {title}")
                lines.append("")
                lines.append(str(requirement.get("description", "")))
                lines.append("")

        return "\n".join(lines).strip() + "\n"


markdown_output_agent = MarkdownOutputAgent()
