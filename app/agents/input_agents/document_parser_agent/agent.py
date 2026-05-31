# EN: Input agent for converting supported uploaded files into structured text.
# KO: 지원되는 업로드 파일을 구조화된 텍스트로 변환하는 Input Agent입니다.

from pathlib import PurePath

from pydantic import BaseModel, Field


class ParsedDocument(BaseModel):
    text: str = Field(..., description="Extracted plain text")
    parser_name: str = Field(..., description="Parser implementation name")
    metadata: dict = Field(default_factory=dict, description="Parser metadata")


class DocumentParserAgent:
    """Converts external document bytes into structured text for ingestion."""

    SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json", ".log"}
    AGENT_NAME = "DocumentParserAgent"

    async def parse(self, *, file_name: str, file_bytes: bytes) -> ParsedDocument | None:
        extension = PurePath(file_name).suffix.lower()
        if extension not in self.SUPPORTED_EXTENSIONS:
            return None

        text = self._decode_text(file_bytes)
        if not text.strip():
            return None

        return ParsedDocument(
            text=text,
            parser_name=self.AGENT_NAME,
            metadata={
                "file_name": file_name,
                "extension": extension,
                "byte_size": len(file_bytes),
            },
        )

    def _decode_text(self, file_bytes: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "cp949"):
            try:
                return file_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue

        return file_bytes.decode("utf-8", errors="ignore")


document_parser_agent = DocumentParserAgent()
