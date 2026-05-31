# EN: Tests for the document parser input agent.
# KO: 문서 파서 Input Agent 테스트입니다.

import pytest

from app.agents.input_agents.document_parser_agent.agent import DocumentParserAgent
from app.schemas.io_agent import InputAgentRequest, InputFilePayload, InputType


@pytest.mark.anyio
async def test_document_parser_agent_parses_supported_text_file() -> None:
    parser = DocumentParserAgent()

    response = await parser.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.FILE,
            files=[
                InputFilePayload(
                    file_name="requirements.txt",
                    file_bytes="로그인 요구사항".encode("utf-8"),
                )
            ],
        )
    )

    assert response.success is True
    assert response.structured_context["text"] == "로그인 요구사항"
    assert response.structured_context["metadata"]["extension"] == ".txt"


@pytest.mark.anyio
async def test_document_parser_agent_skips_unsupported_file() -> None:
    parser = DocumentParserAgent()

    response = await parser.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.FILE,
            files=[
                InputFilePayload(
                    file_name="requirements.pdf",
                    file_bytes=b"%PDF",
                )
            ],
        )
    )

    assert response.success is False
    assert response.error == "unsupported file extension"
    assert response.validation_errors == ["unsupported file extension"]
