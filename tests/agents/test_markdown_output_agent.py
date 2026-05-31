# EN: Tests for the Markdown output agent contract.
# KO: Markdown Output Agent 계약 테스트입니다.

import pytest

from app.agents.output_agents.markdown_agent.agent import MarkdownOutputAgent
from app.schemas.io_agent import OutputAgentRequest


@pytest.mark.anyio
async def test_markdown_output_agent_renders_requirement_artifact() -> None:
    agent = MarkdownOutputAgent()

    response = await agent.render(
        OutputAgentRequest(
            project_id="PRJ-001",
            artifact_id="ART-001",
            artifact_type="REQUIREMENT_SPEC",
            result_json={
                "artifact_type": "REQUIREMENT_SPEC",
                "requirements": [
                    {
                        "requirement_id": "RQ-001",
                        "title": "Login",
                        "description": "Users can sign in.",
                    }
                ],
            },
        )
    )

    assert response.success is True
    assert response.result is not None
    assert response.result["format"] == "markdown"
    assert "# REQUIREMENT_SPEC" in response.result["content"]
    assert "## Login" in response.result["content"]


@pytest.mark.anyio
async def test_markdown_output_agent_rejects_unsupported_format() -> None:
    agent = MarkdownOutputAgent()

    response = await agent.render(
        OutputAgentRequest(
            project_id="PRJ-001",
            artifact_type="REQUIREMENT_SPEC",
            result_json={"artifact_type": "REQUIREMENT_SPEC"},
            output_format="pdf",
        )
    )

    assert response.success is False
    assert response.error == "unsupported output format"
