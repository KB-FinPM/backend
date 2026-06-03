# EN: Tests for user input normalization orchestration.
# KO: 사용자 입력 표준화 Orchestrator 테스트입니다.

import pytest

from app.orchestrator.input_orchestrator import InputOrchestrator
from app.schemas.io_agent import (
    InputAgentRequest,
    InputFilePayload,
    InputType,
    NormalizedRequestType,
)


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


@pytest.mark.anyio
async def test_input_orchestrator_normalizes_artifact_request() -> None:
    orchestrator = InputOrchestrator()

    response = await orchestrator.normalize(
        InputAgentRequest(
            project_id="PRJ-001",
            permission_scope=["project:PRJ-001:write"],
            input_type=InputType.ARTIFACT_REQUEST,
            raw_payload={"target_artifact_type": "REQUIREMENT_SPEC"},
            context={"source_document_ids": ["DOC-001"]},
        )
    )

    assert response.success is True
    assert response.normalized_request_type == NormalizedRequestType.ARTIFACT_GENERATION
    assert response.structured_context["raw_payload"] == {
        "target_artifact_type": "REQUIREMENT_SPEC"
    }
    assert response.structured_context["context"] == {
        "source_document_ids": ["DOC-001"]
    }
    assert response.structured_context["permission_scope"] == ["project:PRJ-001:write"]
