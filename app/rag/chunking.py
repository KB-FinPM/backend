# EN: Text chunking helpers for document ingestion.
# KO: 문서 수집 과정에서 사용하는 텍스트 chunking 유틸리티입니다.

from pydantic import BaseModel, Field


class TextChunk(BaseModel):
    chunk_index: int = Field(..., description="Zero-based chunk index")
    text: str = Field(..., description="Chunk text")
    section_title: str | None = Field(None, description="Detected section title")
    metadata: dict = Field(default_factory=dict, description="Chunk metadata")


def split_text_into_chunks(
    text: str,
    *,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[TextChunk]:
    normalized_text = "\n".join(
        line.strip() for line in text.splitlines() if line.strip()
    )
    if not normalized_text:
        return []

    chunks: list[TextChunk] = []
    start = 0
    text_length = len(normalized_text)

    while start < text_length:
        current_start = start
        end = min(start + max_chars, text_length)
        if end < text_length:
            split_at = normalized_text.rfind("\n", start, end)
            if split_at <= start:
                split_at = normalized_text.rfind(" ", start, end)
            if split_at > start:
                end = split_at
            if end <= start:
                end = min(start + max_chars, text_length)

        chunk_text = normalized_text[start:end].strip()
        if chunk_text:
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    text=chunk_text,
                    section_title=_detect_section_title(chunk_text),
                    metadata={
                        "start_char": start,
                        "end_char": end,
                    },
                )
            )

        if end >= text_length:
            break

        start = max(end - overlap_chars, current_start + 1)
        while start < text_length and normalized_text[start].isspace():
            start += 1

    return chunks


def _detect_section_title(text: str) -> str | None:
    first_line = text.splitlines()[0].strip()
    if len(first_line) <= 80 and (
        first_line.startswith("#")
        or first_line.endswith(":")
        or first_line.isupper()
    ):
        return first_line.lstrip("#").strip(": ")

    return None
