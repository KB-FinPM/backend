# EN: Input agent for converting supported uploaded files into structured text.
# KO: 지원되는 업로드 파일을 구조화된 텍스트로 변환하는 Input Agent입니다.

from io import BytesIO
from pathlib import PurePath
import re

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

        return InputAgentResponse(
            agent_name=self.AGENT_NAME,
            normalized_request_type=NormalizedRequestType.DOCUMENT_INGESTION,
            structured_context={
                "text": text,
                "metadata": {
                    "file_name": file_payload.file_name,
                    "extension": extension,
                    "byte_size": len(file_payload.file_bytes),
                    "content_type": file_payload.content_type,
                },
            },
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
