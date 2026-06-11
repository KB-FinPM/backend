# EN: Tests for the document parser input agent.
# KO: 문서 파서 Input Agent 테스트입니다.

import pytest
from io import BytesIO
from openpyxl import Workbook

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
async def test_document_parser_agent_extracts_wbs_xlsx_rows() -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "WBS"
    worksheet.append(
        [
            "NO",
            "레벨",
            "ID",
            "WBS명",
            "시작예정일",
            "종료예정일",
            "작업자",
            "산출물",
            "실제시작일",
            "실제종료일",
            "품질프로젝트번호",
            "작업상태",
        ]
    )
    worksheet.append(
        [
            72,
            "4",
            "3.5.1.1",
            "통합테스트설계",
            "2026.05.21",
            "2026.06.16",
            "작업자",
            None,
            None,
            None,
            None,
            None,
        ]
    )
    workbook.create_sheet("GUIDE").append(["업로드 가이드"])
    buffer = BytesIO()
    workbook.save(buffer)

    parser = DocumentParserAgent()
    response = await parser.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.FILE,
            files=[
                InputFilePayload(
                    file_name="WBS (15).xlsx",
                    file_bytes=buffer.getvalue(),
                )
            ],
            context={"document_type": "WBS"},
        )
    )

    assert response.success is True
    wbs_rows = response.structured_context["wbs_context"]["rows"]
    assert wbs_rows[0]["row_number"] == 2
    assert wbs_rows[0]["title"] == "통합테스트설계"
    assert wbs_rows[0]["planned_start_date"] == "2026.05.21"
    assert wbs_rows[0]["raw_assignee"] == "작업자"
