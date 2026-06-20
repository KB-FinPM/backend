import json
from pathlib import Path

import pytest

from app.agents.output_agents.chat_agent.agent import ChatOutputAgent
from app.schemas.io_agent import OutputAgentRequest, OutputResponseType


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "agent_accuracy_learning_seed_cases.json"
)


def _output_cases() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["output_agent_cases"]


@pytest.mark.anyio
@pytest.mark.parametrize("case", _output_cases(), ids=lambda case: case["event"])
async def test_chat_output_agent_seed_correction_messages(case: dict) -> None:
    response = await ChatOutputAgent().render(
        OutputAgentRequest(
            project_id="PRJ-001",
            response_type=OutputResponseType.CHAT_RESPONSE,
            result_json=case["result_json"],
        )
    )

    assert response.success is True
    for expected in case["expected_user_message_contains"]:
        assert expected in response.message
    for forbidden in case["forbidden_internal_terms"]:
        assert forbidden not in response.message
    assert response.display_payload["corrections"] == case["result_json"]["corrections"]
