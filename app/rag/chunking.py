# EN: Text chunking helpers for document ingestion.
# KO: 문서 수집 과정에서 사용하는 텍스트 chunking 유틸리티입니다.

import hashlib
import re

from pydantic import BaseModel, Field


class TextChunk(BaseModel):
    chunk_index: int = Field(..., description="Zero-based chunk index")
    text: str = Field(..., description="Chunk text")
    section_title: str | None = Field(None, description="Detected section title")
    metadata: dict = Field(default_factory=dict, description="Chunk metadata")


def _make_id(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _split_by_headings(text: str) -> list[dict]:
    """sample_0605 semantic heading splitter.

    Keeping this behavior makes RequirementAgent receive chunks in nearly the
    same unit as the standalone sample. It is especially important for long
    table-driven requirement documents where one domain block should be kept
    together when possible.
    """
    lines = text.splitlines()
    sections: list[dict] = []
    current_title = "ROOT"
    current_path = ["ROOT"]
    buffer: list[str] = []
    heading_pattern = re.compile(r"^(\d+(\.\d+)*\s+.+|#{1,6}\s+.+|[가-힣A-Za-z0-9 ]+\s*[>:：])$")
    for line in lines:
        clean = line.strip()
        if heading_pattern.match(clean) and buffer:
            section_text = "\n".join(buffer).strip()
            if section_text:
                sections.append({"title": current_title, "section_path": current_path[:], "text": section_text})
            current_title = clean
            current_path = ["ROOT", current_title]
            buffer = []
        else:
            buffer.append(line)
    if buffer:
        section_text = "\n".join(buffer).strip()
        if section_text:
            sections.append({"title": current_title, "section_path": current_path[:], "text": section_text})
    return sections


def _split_long_text_by_chars(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(chunk_text)
        if end >= len(text):
            break
        start = max(0, end - overlap_chars)
    return chunks


def split_text_into_chunks(
    text: str,
    *,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[TextChunk]:
    # Do not strip or collapse table rows. DOCX table extraction uses pipes and
    # blank cells to preserve column positions.
    normalized_text = "\n".join(line.rstrip() for line in text.splitlines() if line.strip())
    if not normalized_text:
        return []

    chunks: list[TextChunk] = []
    for section in _split_by_headings(normalized_text):
        section_text = section["text"]
        if len(section_text) <= max_chars:
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    text=section_text,
                    section_title=section["title"],
                    metadata={
                        "section_path": section["section_path"],
                        "semantic_chunk_id": _make_id(f"{section['title']}:{section_text[:300]}"),
                    },
                )
            )
            continue
        for idx, part_text in enumerate(_split_long_text_by_chars(section_text, max_chars, overlap_chars), start=1):
            title = f"{section['title']} / part-{idx}"
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    text=part_text,
                    section_title=title,
                    metadata={
                        "section_path": section["section_path"] + [f"part-{idx}"],
                        "semantic_chunk_id": _make_id(f"{section['title']}:{idx}:{part_text[:300]}"),
                    },
                )
            )
    return chunks
