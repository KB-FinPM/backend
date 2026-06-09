# EN: Tests for the document parser input agent.
# KO: 문서 파서 Input Agent 테스트입니다.

from io import BytesIO

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


@pytest.mark.anyio
async def test_document_parser_agent_preserves_docx_table_cell_bullets() -> None:
    from docx import Document

    document = Document()
    table = document.add_table(rows=1, cols=3)
    table.cell(0, 0).text = "환율 관리"
    table.cell(0, 1).text = "고시 관리"

    description_cell = table.cell(0, 2)
    description_cell.text = ""
    description_cell.paragraphs[0].style = "List Bullet"
    description_cell.paragraphs[0].add_run("실시간 환율 채집 및 고시 관리 기능")
    paragraph = description_cell.add_paragraph("시장 LP 및 CMBS로부터의 시장 환율을 채집 및 고시")
    paragraph.style = "List Bullet 2"
    paragraph = description_cell.add_paragraph("Pricing 기능")
    paragraph.style = "List Bullet"

    buffer = BytesIO()
    document.save(buffer)

    parser = DocumentParserAgent()
    response = await parser.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.FILE,
            files=[
                InputFilePayload(
                    file_name="requirements.docx",
                    file_bytes=buffer.getvalue(),
                )
            ],
        )
    )

    assert response.success is True
    assert response.structured_context["text"] == (
        "환율 관리 | 고시 관리 | "
        "o 실시간 환율 채집 및 고시 관리 기능\\n"
        "- 시장 LP 및 CMBS로부터의 시장 환율을 채집 및 고시\\n"
        "o Pricing 기능"
    )
