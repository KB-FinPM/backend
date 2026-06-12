from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath


SUPPORTED_FILE_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".docx",
        ".xlsx",
        ".txt",
        ".md",
        ".markdown",
        ".csv",
        ".json",
        ".log",
    }
)

SUPPORTED_MIME_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "application/csv": ".csv",
    "application/json": ".json",
    "application/x-ndjson": ".json",
}

GENERIC_MIME_TYPES = {
    "",
    "application/octet-stream",
    "binary/octet-stream",
}

SUPPORTED_FILE_TYPE_MESSAGE = (
    "지원하지 않는 파일 형식입니다. PDF, DOCX, XLSX, TXT 파일을 업로드해주세요."
)


@dataclass(frozen=True)
class SupportedFileType:
    extension: str
    content_type: str
    matched_by: str


def normalize_extension(file_name: str | None) -> str:
    return PurePath(file_name or "").suffix.lower()


def normalize_content_type(content_type: str | None) -> str:
    return str(content_type or "").split(";", 1)[0].strip().lower()


def resolve_supported_file_type(
    *,
    file_name: str | None,
    content_type: str | None = None,
) -> SupportedFileType | None:
    extension = normalize_extension(file_name)
    normalized_content_type = normalize_content_type(content_type)
    mime_extension = SUPPORTED_MIME_TYPES.get(normalized_content_type)

    if extension in SUPPORTED_FILE_EXTENSIONS:
        return SupportedFileType(
            extension=extension,
            content_type=normalized_content_type,
            matched_by="extension",
        )

    if extension:
        return None

    if mime_extension:
        return SupportedFileType(
            extension=mime_extension,
            content_type=normalized_content_type,
            matched_by="mime",
        )

    if normalized_content_type in GENERIC_MIME_TYPES and not extension:
        return None

    return None


def supported_extensions_for_display() -> list[str]:
    preferred_order = [".pdf", ".docx", ".xlsx", ".txt", ".md", ".csv", ".json", ".log"]
    return [
        extension
        for extension in preferred_order
        if extension in SUPPORTED_FILE_EXTENSIONS
    ]
