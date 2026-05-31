# EN: Output agent for rendering structured artifacts as Markdown.
# KO: 구조화된 산출물을 Markdown으로 렌더링하는 Output Agent입니다.

from typing import Any

from app.schemas.io_agent import OutputAgentRequest, OutputAgentResponse


class MarkdownOutputAgent:
    """Converts generated artifact JSON into a Markdown document payload."""

    AGENT_NAME = "MarkdownOutputAgent"

    async def render(self, request: OutputAgentRequest) -> OutputAgentResponse:
        if request.output_format != "markdown":
            return OutputAgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                error="unsupported output format",
            )

        markdown = self._render_markdown(request.result_json)
        return OutputAgentResponse(
            agent_name=self.AGENT_NAME,
            result={
                "format": "markdown",
                "content": markdown,
                "artifact_id": request.artifact_id,
                "artifact_type": request.artifact_type,
            },
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
