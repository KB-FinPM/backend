from __future__ import annotations

import sys
import types
from io import BytesIO

import pytest
from openpyxl import Workbook

from app.agents.input_agents.document_parser_agent.agent import DocumentParserAgent
from app.core.supported_files import SUPPORTED_FILE_TYPE_MESSAGE
from app.schemas.io_agent import InputAgentRequest, InputFilePayload, InputType


def _file_request(
    file_name: str,
    file_bytes: bytes,
    *,
    content_type: str | None = None,
    context: dict | None = None,
) -> InputAgentRequest:
    return InputAgentRequest(
        project_id="PRJ-001",
        input_type=InputType.FILE,
        files=[
            InputFilePayload(
                file_name=file_name,
                file_bytes=file_bytes,
                content_type=content_type,
            )
        ],
        context=context or {},
    )


@pytest.mark.anyio
async def test_document_parser_agent_parses_supported_text_file() -> None:
    parser = DocumentParserAgent()

    response = await parser.parse(
        _file_request("requirements.txt", b"login requirement")
    )

    assert response.success is True
    assert response.structured_context["text"] == "login requirement"
    assert response.structured_context["metadata"]["extension"] == ".txt"


@pytest.mark.anyio
async def test_document_parser_agent_skips_unsupported_file() -> None:
    parser = DocumentParserAgent()

    response = await parser.parse(
        _file_request("requirements.exe", b"binary")
    )

    assert response.success is False
    assert response.error == SUPPORTED_FILE_TYPE_MESSAGE


@pytest.mark.anyio
async def test_document_parser_agent_parses_pdf_case_insensitive_extension(
    monkeypatch,
) -> None:
    class FakePage:
        def extract_text(self) -> str:
            return "PDF requirement"

    class FakePdfReader:
        is_encrypted = False
        pages = [FakePage()]

        def __init__(self, stream) -> None:
            self.stream = stream

    monkeypatch.setitem(sys.modules, "pypdf", types.SimpleNamespace(PdfReader=FakePdfReader))

    parser = DocumentParserAgent()
    response = await parser.parse(
        _file_request(
            "requirements.PDF",
            b"%PDF fake",
            content_type="application/pdf",
        )
    )

    assert response.success is True
    assert response.structured_context["text"] == "PDF requirement"
    assert response.structured_context["metadata"]["extension"] == ".pdf"


@pytest.mark.anyio
async def test_document_parser_agent_explains_empty_pdf_text(monkeypatch) -> None:
    class FakePage:
        def extract_text(self) -> str:
            return ""

    class FakePdfReader:
        is_encrypted = False
        pages = [FakePage()]

        def __init__(self, stream) -> None:
            self.stream = stream

    monkeypatch.setitem(sys.modules, "pypdf", types.SimpleNamespace(PdfReader=FakePdfReader))

    parser = DocumentParserAgent()
    response = await parser.parse(
        _file_request(
            "scanned.pdf",
            b"%PDF fake",
            content_type="application/pdf",
        )
    )

    assert response.success is False
    assert response.error == parser.PDF_EMPTY_TEXT_MESSAGE


@pytest.mark.anyio
async def test_document_parser_agent_extracts_wbs_xlsx_rows() -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "WBS"
    worksheet.append(
        [
            "No",
            "Level",
            "ID",
            "Task Name",
            "Planned Start Date",
            "Planned End Date",
            "Assignee",
            "Deliverable",
            "Actual Start Date",
            "Actual End Date",
            "Status",
        ]
    )
    worksheet.append(
        [
            72,
            "4",
            "3.5.1.1",
            "Integration test design",
            "2026.05.21",
            "2026.06.16",
            "QA",
            "test plan",
            None,
            None,
            "TODO",
        ]
    )
    workbook.create_sheet("GUIDE").append(["upload guide"])
    buffer = BytesIO()
    workbook.save(buffer)

    parser = DocumentParserAgent()
    response = await parser.parse(
        _file_request(
            "WBS (15).xlsx",
            buffer.getvalue(),
            context={"document_type": "WBS"},
        )
    )

    assert response.success is True
    wbs_rows = response.structured_context["wbs_context"]["rows"]
    assert wbs_rows[0]["row_number"] == 2
    assert wbs_rows[0]["title"] == "Integration test design"
    assert wbs_rows[0]["planned_start_date"] == "2026.05.21"
    assert wbs_rows[0]["raw_assignee"] == "QA"


@pytest.mark.anyio
async def test_document_parser_agent_decodes_cp949_text() -> None:
    parser = DocumentParserAgent()
    text = "\uc694\uad6c\uc0ac\ud56d: cp949"

    response = await parser.parse(
        _file_request("requirements.txt", text.encode("cp949"))
    )

    assert response.success is True
    assert response.structured_context["text"] == text


@pytest.mark.anyio
async def test_document_parser_agent_removes_postgres_unsafe_nul_bytes() -> None:
    parser = DocumentParserAgent()

    response = await parser.parse(
        _file_request("requirements.txt", b"alpha\x00beta")
    )

    assert response.success is True
    assert response.structured_context["text"] == "alphabeta"


@pytest.mark.anyio
async def test_document_parser_agent_rejects_nul_only_binary_text() -> None:
    parser = DocumentParserAgent()

    response = await parser.parse(_file_request("requirements.txt", b"\x00\x00"))

    assert response.success is False
    assert response.error == parser.EMPTY_TEXT_MESSAGE


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("file_name", "file_bytes", "expected"),
    [
        ("requirements.md", b"# Requirement", "# Requirement"),
        ("requirements.csv", b"id,name\n1,Login", "id,name\n1,Login"),
        ("requirements.json", b'{"requirements":[]}', '{"requirements":[]}'),
        ("requirements.log", b"[INFO] parsed", "[INFO] parsed"),
    ],
)
async def test_document_parser_agent_parses_supported_text_like_extensions(
    file_name: str,
    file_bytes: bytes,
    expected: str,
) -> None:
    parser = DocumentParserAgent()

    response = await parser.parse(_file_request(file_name, file_bytes))

    assert response.success is True
    assert response.structured_context["text"] == expected
