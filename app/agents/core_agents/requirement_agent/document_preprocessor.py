# EN: Requirement-agent document text normalization helpers.
# KO: 요구사항 Agent 내부 문서 텍스트 정규화 helper입니다.

from __future__ import annotations

from copy import deepcopy
from typing import Any


def normalize_requirement_documents(
    documents: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Normalize retrieved chunks before requirement table extraction.

    The input parser intentionally remains generic. Requirement-specific
    handling such as pipe-table row cleanup and section-title carry-over lives
    here in the core agent boundary.
    """
    normalized: list[dict[str, Any]] = []
    current_title = ""
    for document in sorted(documents or [], key=lambda item: int(item.get("chunk_index") or 0)):
        item = deepcopy(document)
        section_title = str(item.get("section_title") or "").strip()
        if section_title and section_title != "ROOT":
            current_title = section_title
        text = _normalize_pipe_table_text(str(item.get("text") or ""))
        item["text"] = text
        if current_title and not section_title:
            item["section_title"] = current_title
        normalized.append(item)
    return normalized


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
