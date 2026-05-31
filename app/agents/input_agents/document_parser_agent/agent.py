# EN: Input agent for converting supported uploaded files into structured text.
# KO: 지원되는 업로드 파일을 구조화된 텍스트로 변환하는 Input Agent입니다.

from pathlib import PurePath

from app.schemas.io_agent import InputAgentRequest, InputAgentResponse


class DocumentParserAgent:
    """Converts external document bytes into structured text for ingestion."""

    SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json", ".log"}
    AGENT_NAME = "DocumentParserAgent"

    async def parse(self, request: InputAgentRequest) -> InputAgentResponse:
        extension = PurePath(request.file_name).suffix.lower()
        if extension not in self.SUPPORTED_EXTENSIONS:
            return InputAgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                error="unsupported file extension",
            )

        text = self._decode_text(request.file_bytes)
        if not text.strip():
            return InputAgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                error="empty parsed text",
            )

        return InputAgentResponse(
            agent_name=self.AGENT_NAME,
            result={
                "text": text,
                "metadata": {
                    "file_name": request.file_name,
                    "extension": extension,
                    "byte_size": len(request.file_bytes),
                    "content_type": request.content_type,
                },
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
