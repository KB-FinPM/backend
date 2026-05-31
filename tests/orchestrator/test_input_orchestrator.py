# EN: Tests for user input normalization orchestration.
# KO: 사용자 입력 표준화 Orchestrator 테스트입니다.

import pytest

from app.orchestrator.input_orchestrator import InputOrchestrator
from app.schemas.io_agent import InputAgentRequest, InputFilePayload, InputType


@pytest.mark.anyio
async def test_input_orchestrator_routes_file_input_to_document_parser() -> None:
    orchestrator = InputOrchestrator()

    response = await orchestrator.normalize(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.FILE,
            files=[
                InputFilePayload(
                    file_name="requirements.txt",
                    file_bytes=b"requirements",
                )
            ],
        )
    )

    assert response.success is True
    assert response.structured_context["text"] == "requirements"


@pytest.mark.anyio
async def test_input_orchestrator_rejects_unsupported_input_type() -> None:
    orchestrator = InputOrchestrator()

    response = await orchestrator.normalize(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"text": "hello"},
        )
    )

    assert response.success is False
    assert response.error == "unsupported input type"
