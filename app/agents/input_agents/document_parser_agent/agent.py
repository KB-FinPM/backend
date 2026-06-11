# EN: Input agent for converting supported uploaded files into structured text.
# KO: 지원되는 업로드 파일을 구조화된 텍스트로 변환하는 Input Agent입니다.

from io import BytesIO
from pathlib import PurePath
import re
from datetime import date, datetime
from typing import Any

from app.schemas.io_agent import (
    InputAgentRequest,
    InputAgentResponse,
    InputType,
    NormalizedRequestType,
)


class DocumentParserAgent:
    """Converts external document bytes into structured text for ingestion."""

    SUPPORTED_EXTENSIONS = {
        ".txt",
        ".md",
        ".markdown",
        ".csv",
        ".json",
        ".log",
        ".docx",
        ".xlsx",
    }
    AGENT_NAME = "DocumentParserAgent"

    async def parse(self, request: InputAgentRequest) -> InputAgentResponse:
        if request.input_type != InputType.FILE or not request.files:
            return InputAgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                normalized_request_type=NormalizedRequestType.DOCUMENT_INGESTION,
                error="file input is required",
                validation_errors=["file input is required"],
            )

        file_payload = request.files[0]
        extension = PurePath(file_payload.file_name).suffix.lower()
        if extension not in self.SUPPORTED_EXTENSIONS:
            return InputAgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                normalized_request_type=NormalizedRequestType.DOCUMENT_INGESTION,
                error="unsupported file extension",
                validation_errors=["unsupported file extension"],
            )

        try:
            extra_metadata: dict[str, Any] = {}
            if extension == ".xlsx":
                text, extra_metadata = self._extract_xlsx_text(
                    file_payload.file_bytes,
                    file_name=file_payload.file_name,
                    document_type=str(
                        (request.context or {}).get("document_type") or ""
                    ),
                )
            else:
                text = self._extract_text(file_payload.file_bytes, extension)
        except Exception as exc:
            return InputAgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                normalized_request_type=NormalizedRequestType.DOCUMENT_INGESTION,
                error="document parse failed",
                validation_errors=[f"document parse failed: {exc}"],
            )

        text = self._remove_postgresql_unsafe_chars(text)
        if not text.strip():
            return InputAgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                normalized_request_type=NormalizedRequestType.DOCUMENT_INGESTION,
                error="empty parsed text",
                validation_errors=["empty parsed text"],
            )

        metadata = {
            "file_name": file_payload.file_name,
            "extension": extension,
            "byte_size": len(file_payload.file_bytes),
            "content_type": file_payload.content_type,
            **extra_metadata,
        }
        structured_context = {
            "text": text,
            "metadata": metadata,
        }
        if "wbs_context" in extra_metadata:
            structured_context["wbs_context"] = extra_metadata["wbs_context"]

        return InputAgentResponse(
            agent_name=self.AGENT_NAME,
            normalized_request_type=NormalizedRequestType.DOCUMENT_INGESTION,
            structured_context=structured_context,
        )

    def _extract_text(self, file_bytes: bytes, extension: str) -> str:
        if extension == ".docx":
            return self._extract_docx_text(file_bytes)
        return self._decode_text(file_bytes)

    def _extract_docx_text(self, file_bytes: bytes) -> str:
        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError(
                "python-docx is required for .docx uploads. Run `pip install python-docx`."
            ) from exc

        document = Document(BytesIO(file_bytes))
        lines: list[str] = []

        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if text:
                lines.append(text)

        numbering_levels = self._docx_numbering_levels(document)
        for table in document.tables:
            for row in table.rows:
                # sample_0605 preserved table column positions, including empty cells.
                # Removing empty cells shifts columns such as Biz요건ID/요구사항ID and
                # causes requirement extraction to map the wrong values.
                cells = [self._extract_docx_cell_text(cell, numbering_levels) for cell in row.cells]
                if any(cells):
                    lines.append(" | ".join(cells))

        return "\n".join(lines)

    def _extract_xlsx_text(
        self,
        file_bytes: bytes,
        *,
        file_name: str,
        document_type: str,
    ) -> tuple[str, dict[str, Any]]:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise RuntimeError(
                "openpyxl is required for .xlsx uploads. Run `pip install openpyxl`."
            ) from exc

        workbook = load_workbook(
            BytesIO(file_bytes),
            data_only=True,
            read_only=True,
        )
        lines: list[str] = []
        for worksheet in workbook.worksheets:
            lines.append(f"[{worksheet.title}]")
            for row in worksheet.iter_rows(values_only=True):
                values = [self._cell_to_text(value) for value in row]
                while values and not values[-1]:
                    values.pop()
                if any(values):
                    lines.append(" | ".join(values))

        metadata: dict[str, Any] = {
            "sheet_names": workbook.sheetnames,
        }
        if document_type.upper() == "WBS" or "WBS" in workbook.sheetnames:
            wbs_context = self._extract_wbs_context(workbook, file_name=file_name)
            if wbs_context.get("rows"):
                metadata["artifact_type"] = "WBS"
                metadata["wbs_context"] = wbs_context

        return "\n".join(lines), metadata

    def _extract_wbs_context(self, workbook, *, file_name: str) -> dict[str, Any]:
        worksheet = workbook["WBS"] if "WBS" in workbook.sheetnames else workbook.active
        header_row_number = 1
        headers: list[str] = []
        rows: list[dict[str, Any]] = []

        for row_number, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
            values = [self._cell_to_json(value) for value in row]
            candidate_headers = [str(value or "").strip() for value in values]
            if not headers and self._looks_like_wbs_header(candidate_headers):
                headers = candidate_headers
                header_row_number = row_number
                continue
            if not headers or row_number <= header_row_number:
                continue

            row_data = {
                headers[index]: values[index]
                for index in range(min(len(headers), len(values)))
                if headers[index]
            }
            if not any(value not in (None, "") for value in row_data.values()):
                continue

            rows.append(
                {
                    **row_data,
                    "row_number": row_number,
                    "no": row_data.get("NO"),
                    "level": row_data.get("레벨"),
                    "wbs_id": row_data.get("ID"),
                    "title": row_data.get("WBS명"),
                    "planned_start_date": row_data.get("시작예정일"),
                    "planned_end_date": row_data.get("종료예정일"),
                    "raw_assignee": row_data.get("작업자"),
                    "artifact": row_data.get("산출물"),
                    "actual_start_date": row_data.get("실제시작일"),
                    "actual_end_date": row_data.get("실제종료일"),
                    "quality_project_no": row_data.get("품질프로젝트번호"),
                    "raw_status": row_data.get("작업상태"),
                    "source_document_name": file_name,
                }
            )

        return {
            "source_document_name": file_name,
            "sheet_name": worksheet.title,
            "header_row_number": header_row_number,
            "columns": {
                "no": "NO",
                "level": "레벨",
                "id": "ID",
                "title": "WBS명",
                "planned_start_date": "시작예정일",
                "planned_end_date": "종료예정일",
                "assignee": "작업자",
                "artifact": "산출물",
                "actual_start_date": "실제시작일",
                "actual_end_date": "실제종료일",
                "quality_project_no": "품질프로젝트번호",
                "status": "작업상태",
            },
            "rows": rows,
        }

    def _looks_like_wbs_header(self, values: list[str]) -> bool:
        header_text = "|".join(values)
        return "WBS명" in header_text and "시작예정일" in header_text and "종료예정일" in header_text

    def _cell_to_text(self, value: Any) -> str:
        normalized = self._cell_to_json(value)
        return "" if normalized is None else str(normalized).strip()

    def _cell_to_json(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str):
            return value.strip()
        return value

    def _extract_docx_cell_text(self, cell, numbering_levels: dict[tuple[str, str], str]) -> str:
        paragraphs: list[str] = []
        for paragraph in cell.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue
            paragraphs.append(self._preserve_docx_list_marker(paragraph, text, numbering_levels))
        # Keep the table row as one physical line while preserving cell-internal
        # paragraph boundaries for downstream table extraction.
        return "\\n".join(paragraphs).strip()

    def _preserve_docx_list_marker(
        self,
        paragraph,
        text: str,
        numbering_levels: dict[tuple[str, str], str],
    ) -> str:
        if self._has_text_bullet_marker(text):
            return text
        list_level = self._docx_list_level(paragraph, numbering_levels)
        if list_level is None:
            return text
        marker = "-" if list_level > 0 else "o"
        return f"{marker} {text}"

    def _has_text_bullet_marker(self, text: str) -> bool:
        return bool(
            re.match(
                r"^\s*(?:[-*•ㅇ○·]|[oO]|\d+[.)]|[①②③④⑤⑥⑦⑧⑨⑩]|[ㄱ-ㅎ]\.)"
                r"(?:\s+|(?=[가-힣A-Z]))",
                text,
            )
        )

    def _is_docx_list_paragraph(self, paragraph) -> bool:
        style_name = str(getattr(getattr(paragraph, "style", None), "name", "") or "").lower()
        if any(token in style_name for token in ["list", "bullet", "number"]):
            return True
        p_pr = getattr(getattr(paragraph, "_p", None), "pPr", None)
        if p_pr is not None and p_pr.numPr is not None:
            return True
        style = getattr(paragraph, "style", None)
        style_p_pr = getattr(getattr(style, "element", None), "pPr", None)
        return bool(style_p_pr is not None and style_p_pr.numPr is not None)

    def _docx_list_level(
        self,
        paragraph,
        numbering_levels: dict[tuple[str, str], str],
    ) -> int | None:
        p_pr = getattr(getattr(paragraph, "_p", None), "pPr", None)
        num_pr = getattr(p_pr, "numPr", None)
        num_id, ilvl_value = self._docx_num_id_and_level(num_pr)
        if ilvl_value is None:
            style = getattr(paragraph, "style", None)
            style_p_pr = getattr(getattr(style, "element", None), "pPr", None)
            style_num_pr = getattr(style_p_pr, "numPr", None)
            num_id, ilvl_value = self._docx_num_id_and_level(style_num_pr)

        if ilvl_value is not None:
            try:
                return int(ilvl_value)
            except (TypeError, ValueError):
                pass

        style_name = str(getattr(getattr(paragraph, "style", None), "name", "") or "")
        match = re.search(r"(\d+)$", style_name)
        if match:
            return max(int(match.group(1)) - 1, 0)
        if self._is_docx_list_paragraph(paragraph):
            return 0
        return None

    def _docx_num_id_and_level(self, num_pr) -> tuple[str | None, str | None]:
        if num_pr is None:
            return None, None
        num_id = getattr(getattr(num_pr, "numId", None), "val", None)
        ilvl = getattr(getattr(num_pr, "ilvl", None), "val", None)
        return (str(num_id) if num_id is not None else None, str(ilvl) if ilvl is not None else None)

    def _docx_numbering_levels(self, document) -> dict[tuple[str, str], str]:
        levels: dict[tuple[str, str], str] = {}
        numbering_part = getattr(getattr(document, "part", None), "numbering_part", None)
        numbering = getattr(numbering_part, "element", None)
        if numbering is None:
            return levels

        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        abstract_num_for_num: dict[str, str] = {}
        for num in numbering.findall("w:num", ns):
            num_id = self._xml_attr(num, "numId")
            abstract = num.find("w:abstractNumId", ns)
            abstract_id = self._xml_attr(abstract, "val")
            if num_id and abstract_id:
                abstract_num_for_num[num_id] = abstract_id

        abstract_levels: dict[tuple[str, str], str] = {}
        for abstract in numbering.findall("w:abstractNum", ns):
            abstract_id = self._xml_attr(abstract, "abstractNumId")
            if not abstract_id:
                continue
            for level in abstract.findall("w:lvl", ns):
                ilvl = self._xml_attr(level, "ilvl")
                fmt = level.find("w:numFmt", ns)
                num_fmt = self._xml_attr(fmt, "val") or ""
                if ilvl is not None:
                    abstract_levels[(abstract_id, ilvl)] = num_fmt

        for num_id, abstract_id in abstract_num_for_num.items():
            for (candidate_id, ilvl), num_fmt in abstract_levels.items():
                if candidate_id == abstract_id:
                    levels[(num_id, ilvl)] = num_fmt
        return levels

    def _xml_attr(self, element, name: str) -> str | None:
        if element is None:
            return None
        return element.get(f"{{http://schemas.openxmlformats.org/wordprocessingml/2006/main}}{name}")

    def _decode_text(self, file_bytes: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "cp949"):
            try:
                return file_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue

        return file_bytes.decode("utf-8", errors="ignore")

    def _remove_postgresql_unsafe_chars(self, text: str) -> str:
        # PostgreSQL text/json columns cannot store NUL bytes. Binary Office files
        # decoded as plain text often contain them, so sanitize before persistence.
        return text.replace("\x00", "")


document_parser_agent = DocumentParserAgent()
