from __future__ import annotations

from typing import Any

from app.core.logger import get_logger

logger = get_logger(__name__)


class MeetingTodoContextRetriever:
    """Best-effort vector context lookup for meeting TODO extraction."""

    def __init__(self, retrieval_service: Any | None = None) -> None:
        self.retrieval_service = retrieval_service

    async def retrieve(
        self,
        *,
        project_id: str,
        permission_scope: list[str],
        query: str,
        document_ids: list[str] | None = None,
        top_k: int = 4,
    ) -> list[dict[str, Any]]:
        if self.retrieval_service is None:
            return []
        try:
            return await self.retrieval_service.search(
                project_id=project_id,
                permission_scope=permission_scope,
                query=query,
                top_k=top_k,
                document_ids=document_ids,
                search_mode="auto",
            )
        except Exception as exc:
            logger.warning(
                "[MeetingTodoContextRetriever] vector context lookup skipped | "
                "project_id=%s | error=%s",
                project_id,
                exc,
            )
            return []
