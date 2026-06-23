# EN: Requirement-agent document text normalization helpers.
# KO: 요구사항 Agent 내부 문서 텍스트 정규화 helper입니다.

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from util.agent_generation_utils import split_requirement_detail_items


MEETING_NOTE_TYPE_VALUES = {
    "MEETING_NOTES",
    "MEETING_NOTE",
    "MEETING_MINUTES",
}
MEETING_NOTE_KEYWORDS = (
    "회의록",
    "회의 내용",
    "회의내용",
    "미팅 내용",
    "미팅내용",
    "minutes",
    "meeting note",
    "meeting notes",
)


def normalize_requirement_documents(
    documents: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Normalize retrieved chunks before requirement table extraction.

    The input parser intentionally remains generic. Requirement-specific
    handling such as pipe-table row cleanup and section-title carry-over lives
    here in the core agent boundary.
    """
    normalized: list[dict[str, Any]] = []
    current_title_by_document_id: dict[str, str] = {}
    for document in documents or []:
        item = deepcopy(document)
        document_id = str(item.get("document_id") or "").strip()
        document_key = document_id or "__default__"
        section_title = str(item.get("section_title") or "").strip()
        if section_title and section_title != "ROOT":
            current_title_by_document_id[document_key] = section_title
        text = _normalize_pipe_table_text(str(item.get("text") or ""))
        meeting_note_chunks = _meeting_note_requirement_chunks(item, text)
        if meeting_note_chunks:
            for index, chunk_text in enumerate(meeting_note_chunks, start=1):
                chunk_item = deepcopy(item)
                chunk_item["text"] = chunk_text
                chunk_item["chunk_id"] = _meeting_note_chunk_id(
                    chunk_item.get("chunk_id"),
                    document_key,
                    index,
                )
                if section_title and not chunk_item.get("section_title"):
                    chunk_item["section_title"] = section_title
                normalized.append(chunk_item)
            continue
        item["text"] = text
        current_title = current_title_by_document_id.get(document_key, "")
        if current_title and not section_title:
            item["section_title"] = current_title
        normalized.append(item)
    return normalized


def _meeting_note_requirement_chunks(
    document: dict[str, Any],
    text: str,
) -> list[str]:
    if not _is_meeting_note_document(document):
        return []

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    chunks: list[str] = []
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = line.replace("|", "\n")
        for candidate in split_requirement_detail_items(line):
            cleaned = _normalize_meeting_note_item(candidate)
            if _looks_like_meeting_note_requirement(cleaned):
                chunks.append(cleaned)

    if len(chunks) <= 1:
        return []
    return _dedupe_preserve_order(chunks)


def _is_meeting_note_document(document: dict[str, Any]) -> bool:
    metadata = document.get("metadata") or {}
    document_type = str(
        metadata.get("document_type")
        or metadata.get("source_document_type")
        or metadata.get("documentType")
        or metadata.get("sourceDocumentType")
        or "",
    ).upper()
    if document_type in MEETING_NOTE_TYPE_VALUES:
        return True

    haystack = " ".join(
        str(value or "")
        for value in (
            document.get("section_title"),
            metadata.get("source_file_name"),
            metadata.get("document_file_name"),
            metadata.get("file_name"),
        )
    ).lower()
    return any(keyword in haystack for keyword in MEETING_NOTE_KEYWORDS)


def _normalize_meeting_note_item(value: str) -> str:
    text = str(value or "").replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip(" -•ㅇ○·")
    text = re.sub(r"^\d+(?:[-.]\d+)*\.\s*", "", text)
    text = re.sub(r"^\d+[\).]\s*", "", text)
    text = re.sub(r"^(?:회의록|회의 내용|회의내용|미팅 내용|미팅내용)\s*[:：-]\s*", "", text)
    return text.strip()


def _looks_like_meeting_note_requirement(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if len(text) < 6:
        return False
    return bool(
        re.search(
            r"(구현|개선|제공|조회|등록|수정|삭제|검색|기능|화면|처리|관리|연계|배치|권한|보안|테스트|검토|설정|고시|채집|Pricing|API)",
            text,
            flags=re.IGNORECASE,
        )
    )


def _meeting_note_chunk_id(chunk_id: Any, document_key: str, index: int) -> str:
    base = str(chunk_id or document_key or "MEETING").strip() or "MEETING"
    return f"{base}#note-{index:03d}"


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _normalize_pipe_table_text(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if "|" in line:
            cells = [cell.strip() for cell in line.split("|")]
            line = " | ".join(cells)
        lines.append(line)
    return "\n".join(lines)
