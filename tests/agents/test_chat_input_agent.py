# EN: Tests for natural chat input intent normalization.

import pytest

from app.agents.input_agents.chat_input_agent.agent import ChatInputAgent
from app.schemas.io_agent import InputAgentRequest, InputType


@pytest.mark.anyio
async def test_chat_input_agent_detects_wbs_generation_intent() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "이 요구사항으로 WBS 만들어줘"},
            context={"selected_document_ids": ["DOC-REQ-001"]},
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "GENERATE_ARTIFACT"
    assert response.structured_context["target_artifact_type"] == "WBS"
    assert response.structured_context["source_document_ids"] == ["DOC-REQ-001"]


@pytest.mark.anyio
async def test_chat_input_agent_detects_confirmation_command() -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "생성해"},
        )
    )

    assert response.success is True
    assert response.structured_context["intent"] == "CONFIRM_PENDING_ACTION"
