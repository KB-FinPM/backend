# EN: Tests for the document parser input agent.
# KO: 문서 파서 Input Agent 테스트입니다.

import pytest

from app.agents.input_agents.document_parser_agent.agent import DocumentParserAgent
from app.schemas.io_agent import InputAgentRequest


@pytest.mark.anyio
async def test_document_parser_agent_parses_supported_text_file() -> None:
    parser = DocumentParserAgent()

    response = await parser.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            file_name="requirements.txt",
            file_bytes="로그인 요구사항".encode("utf-8"),
        )
    )

    assert response.success is True
    assert response.result is not None
    assert response.result["text"] == "로그인 요구사항"
    assert response.result["metadata"]["extension"] == ".txt"


@pytest.mark.anyio
async def test_document_parser_agent_skips_unsupported_file() -> None:
    parser = DocumentParserAgent()

    response = await parser.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            file_name="requirements.pdf",
            file_bytes=b"%PDF",
        )
    )

    assert response.success is False
    assert response.error == "unsupported file extension"
