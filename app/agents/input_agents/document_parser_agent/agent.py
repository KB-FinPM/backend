# EN: Input agent for converting supported uploaded files into structured text.
# KO: 지원되는 업로드 파일을 구조화된 텍스트로 변환하는 Input Agent입니다.

from io import BytesIO
from pathlib import PurePath

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

        for table in document.tables:
            for row in table.rows:
                # sample_0605 preserved table column positions, including empty cells.
                # Removing empty cells shifts columns such as Biz요건ID/요구사항ID and
                # causes requirement extraction to map the wrong values.
                cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                if any(cells):
                    lines.append(" | ".join(cells))

        return "\n".join(lines)

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
