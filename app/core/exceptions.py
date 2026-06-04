# EN: Application-level exceptions and helpers for API error responses.
# KO: API 오류 응답을 위한 애플리케이션 예외와 헬퍼입니다.

from typing import Any


class ApiError(Exception):
    """Exception type converted into a structured HTTP error response."""

    def __init__(
        self,
        *,
        status_code: int,
        error_code: str,
        message: str,
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.detail = detail
