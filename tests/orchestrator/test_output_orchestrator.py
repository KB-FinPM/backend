# EN: Tests for user-facing output formatting orchestration.
# KO: 사용자 응답 후처리 Orchestrator 테스트입니다.

import pytest

from app.orchestrator.output_orchestrator import OutputOrchestrator
from app.schemas.io_agent import OutputAgentRequest, OutputResponseType


@pytest.mark.anyio
async def test_output_orchestrator_routes_markdown_export() -> None:
    orchestrator = OutputOrchestrator()

    response = await orchestrator.format(
        OutputAgentRequest(
            project_id="PRJ-001",
            response_type=OutputResponseType.ARTIFACT_EXPORT,
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
    assert response.display_payload["format"] == "markdown"


@pytest.mark.anyio
async def test_output_orchestrator_formats_api_response() -> None:
    orchestrator = OutputOrchestrator()

    response = await orchestrator.format(
        OutputAgentRequest(
            project_id="PRJ-001",
            response_type=OutputResponseType.API_RESPONSE,
            result_json={"ok": True},
            message="done",
        )
    )

    assert response.success is True
    assert response.message == "done"
    assert response.display_payload == {"ok": True}


@pytest.mark.anyio
async def test_output_orchestrator_routes_chat_response() -> None:
    orchestrator = OutputOrchestrator()

    response = await orchestrator.format(
        OutputAgentRequest(
            project_id="PRJ-001",
            response_type=OutputResponseType.CHAT_RESPONSE,
            result_json={
                "event": "CONFIRMATION_REQUIRED",
                "pending_action": {
                    "action_id": "ACT-001",
                    "action_type": "GENERATE_WBS",
                    "payload": {
                        "target_artifact_type": "WBS",
                        "source_document_ids": ["DOC-REQ-001"],
                    },
                },
            },
        )
    )

    assert response.success is True
    assert response.display_payload["state"] == "WAITING_CONFIRMATION"
    assert response.display_payload["suggested_actions"][0]["type"] == (
        "CONFIRM_PENDING_ACTION"
    )
